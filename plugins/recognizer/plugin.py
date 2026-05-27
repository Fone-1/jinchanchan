"""图像识别插件 MVP — 识别商店弈子、金币、等级"""

import logging
import re
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

# 金铲铲之战常见 UI 区域坐标（基于 1280x720 分辨率）
# 这些值需要根据实际截图校准，此处为初始占位
REGIONS = {
    "shop": (200, 580, 880, 120),    # 商店区域 [x, y, w, h]
    "gold": (40, 540, 80, 40),       # 金币区域
    "level": (40, 490, 80, 40),      # 等级区域
    "stage": (560, 10, 160, 40),     # 阶段区域
}


class RecognizerPlugin(BasePlugin):
    name = "recognizer"

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._season = config.get("season", "s14")
        self._templates_dir = Path(__file__).parent.parent.parent / "templates" / self._season
        self._champion_templates: dict[str, np.ndarray] = {}
        self._emulator_width = config.get("emulator_width", 1280)
        self._emulator_height = config.get("emulator_height", 720)

        # OCR 引擎和缓存数据
        self._ocr = None
        self._champions_list: list[str] = []
        self._last_gold = 0
        self._last_level = 1

        self.event_bus.on("screenshot_ready", self._on_screenshot)

    def init(self) -> None:
        self._load_templates()
        self._load_champions_list()
        logger.info(f"图像识别插件初始化完成，已加载 {len(self._champion_templates)} 个模板")

    def start(self) -> None:
        self._running = True
        # 后台线程初始化 OCR，避免卡住 UI 启动
        import threading
        threading.Thread(target=self._init_ocr, daemon=True).start()

    def _init_ocr(self) -> None:
        if self._ocr is not None:
            return
        try:
            from paddleocr import PaddleOCR
            # use_angle_cls=False: 不需要检测文字方向，提升速度
            # show_log=False: 隐藏详细日志，避免刷屏
            # lang="ch": 中文识别
            self._ocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang="ch",
                enable_mkldnn=False
            )
            logger.info("PaddleOCR 引擎初始化成功")
        except Exception as e:
            logger.error(f"初始化 PaddleOCR 失败: {e}")

    def _load_champions_list(self) -> None:
        champs_file = Path(__file__).parent.parent.parent / "data" / self._season / "champions.json"
        if champs_file.exists():
            try:
                with open(champs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._champions_list = list(data.keys())
                logger.info(f"已从 {self._season} 载入 {len(self._champions_list)} 个合法弈子名单进行 OCR 过滤")
            except Exception as e:
                logger.error(f"加载弈子列表失败: {e}")

    def stop(self) -> None:
        self._running = False

    def _load_templates(self) -> None:
        champ_dir = self._templates_dir / "champions"
        if not champ_dir.exists():
            logger.warning(f"模板目录不存在: {champ_dir}")
            return
        for img_path in champ_dir.glob("*.png"):
            name = img_path.stem
            tpl = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if tpl is not None:
                self._champion_templates[name] = tpl

    def _on_screenshot(self, img: np.ndarray) -> None:
        if not self._running:
            return
        game_state = self._analyze(img)
        if game_state:
            self.event_bus.emit("game_state_updated", game_state)

    def _analyze(self, img: np.ndarray) -> dict[str, Any] | None:
        h, w = img.shape[:2]
        scale_x = w / self._emulator_width
        scale_y = h / self._emulator_height

        state = {
            "gold": self._read_gold(img, scale_x, scale_y),
            "level": self._read_level(img, scale_x, scale_y),
            "shop_champions": self._recognize_shop(img, scale_x, scale_y),
            "raw_image": img,
        }
        return state

    def _crop_region(self, img: np.ndarray, region_key: str, sx: float, sy: float) -> np.ndarray:
        x, y, rw, rh = REGIONS[region_key]
        x1, y1 = int(x * sx), int(y * sy)
        x2, y2 = int((x + rw) * sx), int((y + rh) * sy)
        return img[y1:y2, x1:x2]

    def _preprocess_for_ocr(self, roi: np.ndarray) -> np.ndarray:
        """对小图像区域进行预处理，优化 OCR 识别"""
        if roi is None or roi.size == 0:
            return roi
        # 转灰度
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # 双三次插值放大 2 倍，有助于小文字识别
        h, w = gray.shape
        resized = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        # 转回 3 通道以满足 PaddleOCR 对多通道图像的维度假设
        bgr = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
        return bgr

    def _parse_ocr_text(self, result: list | None) -> str:
        """从 PaddleOCR 结果中提取文本，支持传统列表格式与新版本 dict 格式"""
        if not result or not isinstance(result, list) or len(result) == 0:
            return ""
        item = result[0]
        if item is None:
            return ""
        if isinstance(item, dict):
            # 新版本 paddlex 格式: [{'rec_texts': ['text1', ...], ...}]
            texts = item.get('rec_texts', [])
            return "".join(texts)
        elif isinstance(item, list):
            # 传统 paddleocr 格式: [ [ [ [box], (text, score) ], ... ] ]
            return "".join([line[1][0] for line in item if line and len(line) > 1])
        return ""

    def _read_gold(self, img: np.ndarray, sx: float, sy: float) -> int:
        """读取金币数"""
        if self._ocr is None:
            return self._last_gold
        roi = self._crop_region(img, "gold", sx, sy)
        processed = self._preprocess_for_ocr(roi)
        try:
            result = self._ocr.ocr(processed)
            text = self._parse_ocr_text(result)
            logger.info(f"Gold OCR raw text: {text}")
            num_str = re.sub(r"\D", "", text)
            if num_str:
                self._last_gold = int(num_str)
        except Exception as e:
            logger.exception("识别金币出错")
        return self._last_gold

    def _read_level(self, img: np.ndarray, sx: float, sy: float) -> int:
        """读取等级"""
        if self._ocr is None:
            return self._last_level
        roi = self._crop_region(img, "level", sx, sy)
        processed = self._preprocess_for_ocr(roi)
        try:
            result = self._ocr.ocr(processed)
            text = self._parse_ocr_text(result)
            logger.info(f"Level OCR raw text: {text}")
            num_str = re.sub(r"\D", "", text)
            if num_str:
                val = int(num_str)
                if 1 <= val <= 10:  # 合法的金铲铲等级在 1 到 10 之间
                    self._last_level = val
        except Exception as e:
            logger.exception("识别等级出错")
        return self._last_level

    def _recognize_shop(self, img: np.ndarray, sx: float, sy: float) -> list[str | None]:
        """识别商店中的 5 个弈子"""
        roi = self._crop_region(img, "shop", sx, sy)
        shop_h, shop_w = roi.shape[:2]
        slot_w = shop_w // 5
        results = []
        for i in range(5):
            slot = roi[:, i * slot_w:(i + 1) * slot_w]
            name = None
            
            # 优先使用 OCR 识别弈子名字
            if self._ocr is not None:
                h_slot, w_slot = slot.shape[:2]
                # 弈子名字通常在卡牌底部的中央或偏左
                y1 = int(h_slot * 0.70)
                y2 = int(h_slot * 0.99)
                x1 = int(w_slot * 0.05)
                x2 = int(w_slot * 0.95)
                name_roi = slot[y1:y2, x1:x2]
                name = self._ocr_champion_name(name_roi)
                
            # 如果 OCR 未识别成功，尝试模板匹配作为备用
            if not name:
                name = self._match_champion(slot)
                
            results.append(name)
        return results

    def _ocr_champion_name(self, roi: np.ndarray) -> str | None:
        """使用 OCR 识别卡槽中的弈子名字"""
        processed = self._preprocess_for_ocr(roi)
        try:
            result = self._ocr.ocr(processed)
            text = self._parse_ocr_text(result)
            cleaned_text = re.sub(r"[^\u4e00-\u9fa5]", "", text)  # 过滤非中文字符
            logger.info(f"Slot OCR raw text: {text} -> cleaned: {cleaned_text}")
            
            if not cleaned_text:
                return None
                
            # 精确匹配或子串匹配合法弈子列表
            if self._champions_list:
                if cleaned_text in self._champions_list:
                    return cleaned_text
                for champ in self._champions_list:
                    if champ in cleaned_text or cleaned_text in champ:
                        return champ
            else:
                return cleaned_text
        except Exception as e:
            logger.exception("OCR 弈子名称识别出错")
        return None

    def _match_champion(self, slot_img: np.ndarray) -> str | None:
        """模板匹配商店弈子头像"""
        if not self._champion_templates:
            return None
        best_name = None
        best_score = 0.0
        slot_gray = cv2.cvtColor(slot_img, cv2.COLOR_BGR2GRAY)
        for name, tpl in self._champion_templates.items():
            tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
            if tpl_gray.shape[0] > slot_gray.shape[0] or tpl_gray.shape[1] > slot_gray.shape[1]:
                continue
            res = cv2.matchTemplate(slot_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_name = name
        if best_score > 0.7:
            return best_name
        return None

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "emulator_width": {"type": "integer", "default": 1280, "label": "模拟器宽度"},
            "emulator_height": {"type": "integer", "default": 720, "label": "模拟器高度"},
        }

"""图像识别插件 MVP — 识别商店弈子、金币、等级"""

import logging
import re
import time
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

# 金铲铲之战 UI 区域坐标（基于 1280x720 分辨率）
REGIONS = {
    "shop": (200, 580, 880, 122),    # 商店区域 [x, y, w, h]
    "gold": (616, 566, 61, 26),      # 金币区域
    "level": (229, 567, 35, 22),      # 等级区域
    "stage": (560, 10, 160, 40),     # 阶段区域
}


class RecognizerPlugin(BasePlugin):
    name = "recognizer"

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._season = config.get("season", "s14")
        self._templates_dir = Path(__file__).parent.parent.parent / "templates" / self._season
        self._champion_templates: dict[str, np.ndarray] = {}  # 灰度模板
        self._emulator_width = config.get("emulator_width", 1280)
        self._emulator_height = config.get("emulator_height", 720)

        # OCR 引擎和缓存数据
        self._ocr = None
        self._champions_list: list[str] = []
        self._champion_set: set[str] = set()  # O(1) 查找
        self._last_gold = 0
        self._last_level = 1

        # 调试模式：保存裁剪区域图片
        self._debug = config.get("debug", False)
        self._debug_dir = Path(__file__).parent.parent.parent / "debug"
        self._debug_count = 0

        # 任务开关状态
        self._task_enabled = False

        self.event_bus.on("screenshot_ready", self._on_screenshot)
        self.event_bus.on("task_toggled", self._on_task_toggled)

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
            from rapidocr_onnxruntime import RapidOCR
            t0 = time.perf_counter()
            self._ocr = RapidOCR()
            elapsed = time.perf_counter() - t0
            logger.info(f"RapidOCR 引擎初始化成功 ({elapsed:.1f}s)")
        except Exception as e:
            logger.error(f"初始化 RapidOCR 失败: {e}")

    def _load_champions_list(self) -> None:
        champs_file = Path(__file__).parent.parent.parent / "data" / self._season / "champions.json"
        if champs_file.exists():
            try:
                with open(champs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._champions_list = list(data.keys())
                    self._champion_set = set(self._champions_list)
                logger.info(f"已从 {self._season} 载入 {len(self._champions_list)} 个合法弈子名单进行 OCR 过滤")
            except Exception as e:
                logger.error(f"加载弈子列表失败: {e}")

    def stop(self) -> None:
        self._running = False

    def _on_task_toggled(self, enabled: bool) -> None:
        self._task_enabled = enabled
        logger.info(f"识别任务{'已启动' if enabled else '已停止'}")

    def _load_templates(self) -> None:
        """加载模板并预处理为灰度图，避免运行时重复转换"""
        champ_dir = self._templates_dir / "champions"
        if not champ_dir.exists():
            logger.warning(f"模板目录不存在: {champ_dir}")
            return
        for img_path in champ_dir.glob("*.png"):
            name = img_path.stem
            tpl = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if tpl is not None:
                self._champion_templates[name] = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)

    def _on_screenshot(self, img: np.ndarray) -> None:
        if not self._running or not self._task_enabled:
            return
        game_state = self._analyze(img)
        if game_state:
            self.event_bus.emit("game_state_updated", game_state)

    def _analyze(self, img: np.ndarray) -> dict[str, Any] | None:
        t_start = time.perf_counter()

        h, w = img.shape[:2]
        scale_x = w / self._emulator_width
        scale_y = h / self._emulator_height

        # 调试模式：保存裁剪区域
        if self._debug and self._debug_count < 3:
            self._save_debug_regions(img, scale_x, scale_y)
            self._debug_count += 1

        gold, level = self._read_gold_and_level(img, scale_x, scale_y)
        shop_champions = self._recognize_shop(img, scale_x, scale_y)

        elapsed = time.perf_counter() - t_start
        logger.info(f"识别完成: {elapsed:.2f}s | 金币={gold} 等级={level} 商店={shop_champions}")

        state = {
            "gold": gold,
            "level": level,
            "shop_champions": shop_champions,
            "raw_image": img,
        }
        return state

    def _save_debug_regions(self, img: np.ndarray, sx: float, sy: float) -> None:
        """保存裁剪区域图片用于调试"""
        self._debug_dir.mkdir(exist_ok=True)
        for region_key in ["gold", "level", "shop"]:
            roi = self._crop_region(img, region_key, sx, sy)
            path = self._debug_dir / f"{region_key}_{self._debug_count}.png"
            cv2.imwrite(str(path), roi)
            logger.info(f"[DEBUG] 保存裁剪区域: {path} (尺寸: {roi.shape})")
        cv2.imwrite(str(self._debug_dir / f"full_{self._debug_count}.png"), img)
        logger.info(f"[DEBUG] 调试图片已保存到 {self._debug_dir}")

    def _crop_region(self, img: np.ndarray, region_key: str, sx: float, sy: float) -> np.ndarray:
        x, y, rw, rh = REGIONS[region_key]
        x1, y1 = int(x * sx), int(y * sy)
        x2, y2 = int((x + rw) * sx), int((y + rh) * sy)
        return img[y1:y2, x1:x2]

    def _preprocess_for_ocr(self, roi: np.ndarray) -> np.ndarray:
        """对小图像区域进行预处理，优化 OCR 识别"""
        if roi is None or roi.size == 0:
            return roi
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        resized = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        return cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)

    def _parse_ocr_text(self, result) -> str:
        """从 RapidOCR 结果中提取文本
        RapidOCR 返回: [[box, text, score], ...] 或 None
        """
        if not result or not isinstance(result, list):
            return ""
        texts = []
        for item in result:
            if item and len(item) >= 2:
                texts.append(str(item[1]))
        return "".join(texts)

    # ── 合并 OCR：金币和等级一次调用 ──

    def _read_gold_and_level(self, img: np.ndarray, sx: float, sy: float) -> tuple[int, int]:
        """一次 OCR 调用同时读取金币和等级"""
        if self._ocr is None:
            return self._last_gold, self._last_level

        gold_roi = self._crop_region(img, "gold", sx, sy)
        level_roi = self._crop_region(img, "level", sx, sy)

        gold_processed = self._preprocess_for_ocr(gold_roi)
        level_processed = self._preprocess_for_ocr(level_roi)

        try:
            gold_result, _ = self._ocr(gold_processed)
            gold_text = self._parse_ocr_text(gold_result)
            num_str = re.sub(r"\D", "", gold_text)
            if num_str:
                self._last_gold = int(num_str)
            logger.info(f"Gold OCR: '{gold_text}' -> {self._last_gold}")
        except Exception:
            logger.exception("识别金币出错")

        try:
            level_result, _ = self._ocr(level_processed)
            level_text = self._parse_ocr_text(level_result)
            num_str = re.sub(r"\D", "", level_text)
            if num_str:
                val = int(num_str)
                if 1 <= val <= 10:
                    self._last_level = val
            logger.info(f"Level OCR: '{level_text}' -> {self._last_level}")
        except Exception:
            logger.exception("识别等级出错")

        return self._last_gold, self._last_level

    # ── 商店识别：逐槽 OCR ──

    def _recognize_shop(self, img: np.ndarray, sx: float, sy: float) -> list[str | None]:
        """识别商店中的 5 个弈子"""
        roi = self._crop_region(img, "shop", sx, sy)
        shop_h, shop_w = roi.shape[:2]
        slot_w = shop_w // 5
        results = []
        for i in range(5):
            slot = roi[:, i * slot_w:(i + 1) * slot_w]
            name = self._ocr_champion_name(slot)
            if not name:
                name = self._match_champion(slot)
            results.append(name)
        return results

    def _ocr_champion_name(self, slot_img: np.ndarray) -> str | None:
        """OCR 识别单个卡槽的弈子名字"""
        if self._ocr is None:
            return None
        h, w = slot_img.shape[:2]
        y1 = int(h * 0.70)
        y2 = int(h * 0.99)
        x1 = int(w * 0.05)
        x2 = int(w * 0.95)
        name_roi = slot_img[y1:y2, x1:x2]
        # 放大到更易识别的尺寸
        bh = name_roi.shape[0]
        if bh < 32:
            scale = 32 / bh
            name_roi = cv2.resize(name_roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        try:
            raw_result, _ = self._ocr(name_roi)
            text = self._parse_ocr_text(raw_result)
            cleaned = re.sub(r"[^一-龥]", "", text)
            if not cleaned:
                return None
            return self._match_champion_name(cleaned)
        except Exception:
            logger.exception("OCR 弈子名称识别出错")
            return None

    def _match_champion_name(self, text: str) -> str | None:
        """将 OCR 文字匹配到合法弈子名"""
        if not text:
            return None
        if text in self._champion_set:
            return text
        for champ in self._champions_list:
            if champ in text or text in champ:
                return champ
        return None

    def _match_champion(self, slot_img: np.ndarray) -> str | None:
        """模板匹配商店弈子头像（模板已预处理为灰度）"""
        if not self._champion_templates:
            return None
        best_name = None
        best_score = 0.0
        slot_gray = cv2.cvtColor(slot_img, cv2.COLOR_BGR2GRAY)
        for name, tpl_gray in self._champion_templates.items():
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

    def get_debug_info(self) -> dict[str, Any]:
        return {
            "season": self._season,
            "templates_loaded": len(self._champion_templates),
            "champions_list_size": len(self._champions_list),
            "ocr_ready": self._ocr is not None,
            "last_gold": self._last_gold,
            "last_level": self._last_level,
            "task_enabled": self._task_enabled,
            "debug_mode": self._debug,
            "debug_images_saved": self._debug_count,
        }

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "emulator_width": {"type": "integer", "default": 1280, "label": "模拟器宽度"},
            "emulator_height": {"type": "integer", "default": 720, "label": "模拟器高度"},
            "debug": {"type": "boolean", "default": False, "label": "调试模式（保存裁剪区域图片）"},
        }

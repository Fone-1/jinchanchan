"""图像识别插件 MVP — 识别商店弈子、金币、等级"""

import logging
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

        self.event_bus.on("screenshot_ready", self._on_screenshot)

    def init(self) -> None:
        self._load_templates()
        logger.info(f"图像识别插件初始化完成，已加载 {len(self._champion_templates)} 个模板")

    def start(self) -> None:
        self._running = True

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

    def _read_gold(self, img: np.ndarray, sx: float, sy: float) -> int:
        """读取金币数 — MVP 先返回 0，后续接入 OCR"""
        # TODO: 接入 PaddleOCR 识别金币数字
        roi = self._crop_region(img, "gold", sx, sy)
        return 0

    def _read_level(self, img: np.ndarray, sx: float, sy: float) -> int:
        """读取等级 — MVP 先返回 0，后续接入 OCR"""
        # TODO: 接入 PaddleOCR 识别等级数字
        roi = self._crop_region(img, "level", sx, sy)
        return 0

    def _recognize_shop(self, img: np.ndarray, sx: float, sy: float) -> list[str | None]:
        """识别商店中的 5 个弈子"""
        roi = self._crop_region(img, "shop", sx, sy)
        shop_w = roi.shape[1]
        slot_w = shop_w // 5
        results = []
        for i in range(5):
            slot = roi[:, i * slot_w:(i + 1) * slot_w]
            name = self._match_champion(slot)
            results.append(name)
        return results

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

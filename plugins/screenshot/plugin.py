"""截图采集插件 — 周期性从模拟器截图，输出到事件总线"""

import logging
import threading
from typing import Any

import cv2
import numpy as np

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class ScreenshotPlugin(BasePlugin):
    name = "screenshot"

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._device = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._interval = self.config.get("interval_ms", 500) / 1000.0
        self._region = self.config.get("region")  # [x, y, w, h] or None

        self.event_bus.on("device_connected", self._on_device_connected)
        self.event_bus.on("device_disconnected", self._on_device_disconnected)

    def init(self) -> None:
        logger.info("截图插件初始化完成")

    def start(self) -> None:
        self._running = True
        if self._device:
            self._start_capture()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _on_device_connected(self, data: dict) -> None:
        self._device = data.get("device")
        if self._running:
            self._start_capture()

    def _on_device_disconnected(self, _data=None) -> None:
        self._device = None
        self._stop_event.set()

    def _start_capture(self) -> None:
        self._stop_event.clear()

        def _capture_loop():
            while not self._stop_event.is_set():
                try:
                    img = self._take_screenshot()
                    if img is not None:
                        self.event_bus.emit("screenshot_ready", img)
                except Exception:
                    logger.exception("截图失败")
                self._stop_event.wait(timeout=self._interval)

        self._thread = threading.Thread(target=_capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"截图采集已启动，间隔 {self._interval}s")

    def _take_screenshot(self) -> np.ndarray | None:
        if self._device is None:
            return None
        raw = self._device.screenshot()
        img = cv2.cvtColor(np.array(raw), cv2.COLOR_RGB2BGR)
        if self._region:
            x, y, w, h = self._region
            img = img[y:y + h, x:x + w]
        return img

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "interval_ms": {"type": "integer", "default": 500, "label": "截图间隔 (ms)"},
            "region": {"type": "string", "default": "", "label": "截图区域 (x,y,w,h 留空全屏)"},
        }

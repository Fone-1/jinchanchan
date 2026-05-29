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
        self._adb = None
        self._device = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._interval = self.config.get("interval_ms", 500) / 1000.0
        self._region = self.config.get("region")  # [x, y, w, h] or None
        self._consecutive_black_frames = 0

        self.event_bus.on("device_connected", self._on_device_connected)
        self.event_bus.on("device_disconnected", self._on_device_disconnected)

    def init(self) -> None:
        logger.info("截图插件初始化完成")

    def start(self) -> None:
        self._running = True
        self._start_capture()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._adb = None
        self._device = None

    def _on_device_connected(self, data: dict) -> None:
        self._adb = data.get("connector")
        self._device = data.get("device")
        self._consecutive_black_frames = 0

    def _on_device_disconnected(self, _data=None) -> None:
        self._adb = None
        self._device = None
        self._consecutive_black_frames = 0

    def _start_capture(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()

        def _capture_loop():
            while not self._stop_event.is_set():
                try:
                    img = self._take_screenshot()
                    if img is not None:
                        if np.all(img == 0):
                            self._consecutive_black_frames += 1
                            logger.warning(f"检测到黑图 (可能截图失败)，连续次数: {self._consecutive_black_frames}/3")
                            if self._consecutive_black_frames >= 3:
                                logger.error("连续 3 次检测到黑图，触发 ADB 重新连接...")
                                self._consecutive_black_frames = 0
                                self.event_bus.emit("request_adb_reconnect")
                                continue
                        else:
                            self._consecutive_black_frames = 0
                            self.event_bus.emit("screenshot_ready", img)
                except Exception:
                    logger.exception("截图失败")
                self._stop_event.wait(timeout=self._interval)

        self._thread = threading.Thread(target=_capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"截图采集已启动，间隔 {self._interval}s")

    def _take_screenshot(self) -> np.ndarray | None:
        if self._adb is not None:
            raw = self._adb.screenshot()
        elif self._device is not None:
            raw = self._device.screenshot()
        else:
            return None
        img = cv2.cvtColor(np.array(raw), cv2.COLOR_RGB2BGR)
        if self._region:
            x, y, w, h = self._region
            img = img[y:y + h, x:x + w]
        return img

    def get_debug_info(self) -> dict[str, Any]:
        return {
            "interval_seconds": self._interval,
            "region": self._region,
            "consecutive_black_frames": self._consecutive_black_frames,
            "has_device": self._device is not None,
            "has_connector": self._adb is not None,
            "capture_thread_alive": self._thread.is_alive() if self._thread else False,
        }

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "interval_ms": {"type": "integer", "default": 500, "label": "截图间隔 (ms)"},
            "region": {"type": "string", "default": "", "label": "截图区域 (x,y,w,h 留空全屏)"},
        }

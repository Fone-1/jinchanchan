"""操作执行插件 MVP — 将操作指令转化为 ADB 点击"""

import logging
import threading
import time
from queue import Queue, Empty
from typing import Any

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

# 商店 5 个卡槽的中心坐标（基于 1280x720）
SHOP_SLOTS = [
    (310, 640),
    (500, 640),
    (690, 640),
    (880, 640),
    (1070, 640),
]

# 其他常用坐标
COORDS = {
    "refresh_button": (1200, 640),   # 刷新商店按钮
    "level_up_button": (1200, 560),  # 升级按钮
    "bench_slots": [                 # 候备席 9 格
        (180, 460), (300, 460), (420, 460),
        (540, 460), (660, 460), (780, 460),
        (900, 460), (1020, 460), (1140, 460),
    ],
}


class ActionExecutorPlugin(BasePlugin):
    name = "action_executor"

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._device = None
        self._queue: Queue = Queue()
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._emulator_width = config.get("emulator_width", 1280)
        self._emulator_height = config.get("emulator_height", 720)

        self.event_bus.on("device_connected", self._on_device_connected)
        self.event_bus.on("device_disconnected", self._on_device_disconnected)
        self.event_bus.on("action_required", self._on_action)

    def init(self) -> None:
        logger.info("操作执行插件初始化完成")

    def start(self) -> None:
        self._running = True
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3)

    def _on_device_connected(self, data: dict) -> None:
        self._device = data.get("device")

    def _on_device_disconnected(self, _data=None) -> None:
        self._device = None

    def _on_action(self, action: dict[str, Any]) -> None:
        """接收决策引擎发来的操作指令"""
        self._queue.put(action)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                action = self._queue.get(timeout=0.5)
            except Empty:
                continue
            try:
                self._execute(action)
                self.event_bus.emit("action_executed", {"action": action, "success": True})
            except Exception as e:
                logger.exception(f"操作执行失败: {action}")
                self.event_bus.emit("action_executed", {"action": action, "success": False, "error": str(e)})

    def _execute(self, action: dict[str, Any]) -> None:
        if self._device is None:
            raise RuntimeError("ADB 设备未连接")

        action_type = action.get("type")

        if action_type == "buy_champion":
            slot = action.get("slot", 0)
            x, y = SHOP_SLOTS[slot]
            self._tap(x, y)

        elif action_type == "refresh_shop":
            x, y = COORDS["refresh_button"]
            self._tap(x, y)

        elif action_type == "level_up":
            x, y = COORDS["level_up_button"]
            self._tap(x, y)

        elif action_type == "move_champion":
            from_pos = action.get("from")
            to_pos = action.get("to")
            self._drag(from_pos, to_pos)

        elif action_type == "sell_champion":
            bench_idx = action.get("bench_index", 0)
            x, y = COORDS["bench_slots"][bench_idx]
            self._tap(x, y, long_press=1000)

        else:
            logger.warning(f"未知操作类型: {action_type}")

    def _tap(self, x: int, y: int, long_press: int = 0) -> None:
        """坐标自适应点击"""
        # 实际坐标按模拟器分辨率缩放
        # adb input tap 使用的是模拟器内部分辨率，通常不需要缩放
        if long_press > 0:
            self._device.shell(f"input swipe {x} {y} {x} {y} {long_press}")
        else:
            self._device.shell(f"input tap {x} {y}")
        logger.debug(f"点击: ({x}, {y})")

    def _drag(self, from_pos: tuple, to_pos: tuple, duration: int = 300) -> None:
        x1, y1 = from_pos
        x2, y2 = to_pos
        self._device.shell(f"input swipe {x1} {y1} {x2} {y2} {duration}")
        logger.debug(f"拖拽: ({x1},{y1}) -> ({x2},{y2})")

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "emulator_width": {"type": "integer", "default": 1280, "label": "模拟器宽度"},
            "emulator_height": {"type": "integer", "default": 720, "label": "模拟器高度"},
        }

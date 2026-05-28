"""调试事件总线 — 继承 EventBus，在 emit/on/off 时记录调试信息"""

import logging
import threading
import time
import traceback
from collections import deque
from typing import Any, Callable

from core.event_bus import EventBus

logger = logging.getLogger(__name__)


class DebugEventBus(EventBus):
    """带调试功能的事件总线，记录所有事件流经信息"""

    def __init__(self, max_events: int = 500):
        super().__init__()
        self._event_log: deque[dict] = deque(maxlen=max_events)
        self._subscription_map: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self._enabled = True

    def on(self, event: str, handler: Callable) -> None:
        """订阅事件，同时记录订阅关系"""
        super().on(event, handler)
        with self._lock:
            if event not in self._subscription_map:
                self._subscription_map[event] = []
            handler_name = getattr(handler, "__qualname__", repr(handler))
            self._subscription_map[event].append(handler_name)

    def off(self, event: str, handler: Callable) -> None:
        """取消订阅，同时更新订阅关系"""
        super().off(event, handler)
        with self._lock:
            if event in self._subscription_map:
                handler_name = getattr(handler, "__qualname__", repr(handler))
                try:
                    self._subscription_map[event].remove(handler_name)
                except ValueError:
                    pass

    def emit(self, event: str, data: Any = None) -> None:
        """发布事件，记录调试信息后调用原始逻辑"""
        if self._enabled:
            self._record_event(event, data)
        super().emit(event, data)

    def _record_event(self, event: str, data: Any) -> None:
        """记录一条事件到环形缓冲区"""
        # 提取调用源模块
        source = "unknown"
        for frame_info in traceback.extract_stack():
            module = frame_info.filename.replace("\\", "/")
            if "debug_event_bus.py" in module:
                continue
            if "event_bus.py" in module:
                continue
            if "plugins/" in module:
                # 提取插件名: plugins/xxx/plugin.py -> xxx
                parts = module.split("plugins/")
                if len(parts) > 1:
                    plugin_part = parts[1].split("/")[0]
                    source = plugin_part
                    break
            elif "ui/" in module:
                source = "ui"
                break
            elif "main.py" in module:
                source = "main"
                break

        # 数据摘要（截断到 200 字符，避免大对象）
        data_summary = ""
        if data is not None:
            try:
                data_summary = repr(data)[:200]
            except Exception:
                data_summary = "<无法序列化>"

        handler_count = len(self._handlers.get(event, []))

        record = {
            "timestamp": time.time(),
            "event_name": event,
            "data_summary": data_summary,
            "handler_count": handler_count,
            "source": source,
        }

        with self._lock:
            self._event_log.append(record)

    def get_event_log(self, event_filter: str = None, limit: int = 100) -> list[dict]:
        """获取事件日志，可按事件名过滤"""
        with self._lock:
            log = list(self._event_log)

        if event_filter:
            log = [r for r in log if event_filter in r["event_name"]]

        return log[-limit:]

    def get_subscription_map(self) -> dict[str, list[str]]:
        """获取当前所有事件订阅关系"""
        with self._lock:
            return {k: list(v) for k, v in self._subscription_map.items()}

    def clear_log(self) -> None:
        """清空事件日志"""
        with self._lock:
            self._event_log.clear()

    def set_enabled(self, enabled: bool) -> None:
        """动态开关调试记录"""
        self._enabled = enabled
        logger.info(f"调试事件记录已{'开启' if enabled else '关闭'}")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

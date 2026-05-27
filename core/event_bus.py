"""事件总线 — 发布/订阅模式，插件间解耦通信"""

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, handler: Callable) -> None:
        """订阅事件"""
        self._handlers[event].append(handler)
        logger.debug(f"订阅事件: {event} -> {handler.__qualname__}")

    def off(self, event: str, handler: Callable) -> None:
        """取消订阅"""
        if handler in self._handlers[event]:
            self._handlers[event].remove(handler)

    def emit(self, event: str, data: Any = None) -> None:
        """发布事件，同步调用所有订阅者"""
        for handler in self._handlers.get(event, []):
            try:
                handler(data)
            except Exception:
                logger.exception(f"事件处理器异常: {event} -> {handler.__qualname__}")

    def clear(self) -> None:
        """清除所有订阅"""
        self._handlers.clear()

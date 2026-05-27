"""插件管理器 — 负责插件的注册、加载、启动、停止"""

import logging
from typing import Any

from core.base_plugin import BasePlugin
from core.event_bus import EventBus

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self, event_bus: EventBus, global_config: dict[str, Any]):
        self.event_bus = event_bus
        self.global_config = global_config
        self._plugins: dict[str, BasePlugin] = {}

    def register(self, plugin_cls: type[BasePlugin], plugin_config: dict[str, Any] | None = None) -> None:
        """注册插件类并实例化"""
        config = plugin_config or {}
        plugin = plugin_cls(self.event_bus, config)
        self._plugins[plugin.name] = plugin
        logger.info(f"插件已注册: {plugin.name}")

    def get(self, name: str) -> BasePlugin | None:
        return self._plugins.get(name)

    def init_all(self) -> None:
        for name, plugin in self._plugins.items():
            try:
                plugin.init()
                logger.info(f"插件已初始化: {name}")
            except Exception:
                logger.exception(f"插件初始化失败: {name}")

    def start_all(self) -> None:
        for name, plugin in self._plugins.items():
            try:
                plugin.start()
                logger.info(f"插件已启动: {name}")
            except Exception:
                logger.exception(f"插件启动失败: {name}")

    def stop_all(self) -> None:
        for name, plugin in self._plugins.items():
            try:
                plugin.stop()
                logger.info(f"插件已停止: {name}")
            except Exception:
                logger.exception(f"插件停止失败: {name}")

    @property
    def plugins(self) -> dict[str, BasePlugin]:
        return self._plugins

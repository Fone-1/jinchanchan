"""调试管理器 — 聚合调试数据，供 UI 消费"""

import logging
from typing import Any

from core.debug_event_bus import DebugEventBus
from core.plugin_manager import PluginManager

logger = logging.getLogger(__name__)


class DebugManager:
    """聚合事件日志、插件状态、订阅关系，提供统一查询接口"""

    def __init__(self, event_bus: DebugEventBus, plugin_manager: PluginManager):
        self._event_bus = event_bus
        self._plugin_manager = plugin_manager

    @property
    def event_bus(self) -> DebugEventBus:
        return self._event_bus

    # ── 事件日志 ──

    def get_event_log(self, event_filter: str = None, limit: int = 100) -> list[dict]:
        return self._event_bus.get_event_log(event_filter, limit)

    def clear_event_log(self) -> None:
        self._event_bus.clear_log()

    def set_monitoring(self, enabled: bool) -> None:
        self._event_bus.set_enabled(enabled)

    @property
    def is_monitoring(self) -> bool:
        return self._event_bus.is_enabled

    # ── 订阅关系 ──

    def get_subscription_map(self) -> dict[str, list[str]]:
        return self._event_bus.get_subscription_map()

    def get_plugin_subscriptions(self, plugin_name: str) -> list[str]:
        """获取某个插件监听的事件列表"""
        subs = self._event_bus.get_subscription_map()
        result = []
        for event, handlers in subs.items():
            for handler in handlers:
                if plugin_name in handler:
                    result.append(event)
                    break
        return result

    # ── 插件状态 ──

    def get_plugin_list(self) -> list[dict]:
        """获取所有插件的基本信息列表"""
        plugins = self._plugin_manager.plugins
        return [
            {
                "name": name,
                "is_running": plugin.is_running,
            }
            for name, plugin in plugins.items()
        ]

    def get_plugin(self, plugin_name: str):
        """获取插件实例"""
        return self._plugin_manager.get(plugin_name)

    def get_plugin_info(self, plugin_name: str) -> dict[str, Any] | None:
        """获取单个插件的详细调试信息"""
        plugin = self._plugin_manager.get(plugin_name)
        if plugin is None:
            return None

        info = {
            "name": plugin.name,
            "is_running": plugin.is_running,
            "config": plugin.config,
            "subscriptions": self.get_plugin_subscriptions(plugin.name),
        }

        # 调用插件自定义的调试信息
        try:
            debug_info = plugin.get_debug_info()
            info["runtime"] = debug_info
        except Exception:
            info["runtime_error"] = "get_debug_info() 执行失败"

        return info

    def get_all_event_names(self) -> list[str]:
        """获取所有已出现过的事件名（用于事件模拟下拉框）"""
        subs = self._event_bus.get_subscription_map()
        return sorted(subs.keys())

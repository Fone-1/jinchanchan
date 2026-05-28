"""插件基类 — 所有插件必须继承此类并实现接口"""

from abc import ABC, abstractmethod
from typing import Any

from core.event_bus import EventBus


class BasePlugin(ABC):
    """插件基类，定义统一生命周期接口"""

    name: str = "unnamed"

    def __init__(self, event_bus: EventBus, config: dict[str, Any]):
        self.event_bus = event_bus
        self.config = config
        self._running = False

    @abstractmethod
    def init(self) -> None:
        """初始化插件资源"""

    @abstractmethod
    def start(self) -> None:
        """启动插件"""

    @abstractmethod
    def stop(self) -> None:
        """停止插件，释放资源"""

    @property
    def is_running(self) -> bool:
        return self._running

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        """返回插件配置项定义，用于 UI 动态生成配置表单"""
        return {}

    def get_debug_info(self) -> dict[str, Any]:
        """返回插件内部运行时状态，供调试面板展示。
        子类可覆写此方法暴露自定义调试信息。"""
        return {}

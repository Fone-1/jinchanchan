"""ADB 连接插件 — 检测模拟器、建立连接、心跳保活"""

import logging
import threading
from typing import Any

from adbutils import AdbClient, AdbDevice

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class AdbConnectorPlugin(BasePlugin):
    name = "adb_connector"

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._client: AdbClient | None = None
        self._device: AdbDevice | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._stop_heartbeat = threading.Event()

    def init(self) -> None:
        host = self.config.get("host", "127.0.0.1")
        port = self.config.get("port", 7555)
        self._client = AdbClient(host=host, port=port)
        logger.info(f"ADB 客户端初始化: {host}:{port}")

    def start(self) -> None:
        self._running = True
        self._connect()
        self._start_heartbeat()

    def stop(self) -> None:
        self._running = False
        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=3)
        self._device = None

    def _connect(self) -> None:
        serial = self.config.get("device_serial")
        try:
            if serial:
                self._device = self._client.device(serial)
            else:
                devices = self._client.device_list()
                if not devices:
                    logger.warning("未检测到 ADB 设备")
                    self.event_bus.emit("device_disconnected")
                    return
                self._device = devices[0]
            info = self._device.shell("getprop ro.product.model").strip()
            logger.info(f"已连接设备: {self._device.serial} ({info})")
            self.event_bus.emit("device_connected", {"device": self._device})
        except Exception:
            logger.exception("ADB 连接失败")
            self._device = None
            self.event_bus.emit("device_disconnected")

    def _start_heartbeat(self) -> None:
        def _heartbeat_loop():
            while not self._stop_heartbeat.is_set():
                self._stop_heartbeat.wait(timeout=5)
                if self._stop_heartbeat.is_set():
                    break
                if self._device is None:
                    self._connect()
                    continue
                try:
                    self._device.shell("echo ok")
                except Exception:
                    logger.warning("ADB 心跳失败，尝试重连")
                    self._device = None
                    self.event_bus.emit("device_disconnected")
                    self._connect()

        self._heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    @property
    def device(self) -> AdbDevice | None:
        return self._device

    @property
    def is_connected(self) -> bool:
        return self._device is not None

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "host": {"type": "string", "default": "127.0.0.1", "label": "ADB 地址"},
            "port": {"type": "integer", "default": 7555, "label": "ADB 端口"},
            "device_serial": {"type": "string", "default": "", "label": "设备序列号（留空自动检测）"},
        }

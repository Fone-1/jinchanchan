"""ADB 连接插件 — 检测模拟器、建立连接、心跳保活、连接测试"""

import logging
import threading
import time
from typing import Any

from adbutils import AdbClient, AdbDevice

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

EMULATOR_PRESETS = {
    "mumu": {"label": "MuMu (默认7555)", "device_port": 7555},
    "leidian": {"label": "雷电 (默认5555)", "device_port": 5555},
    "yeshen": {"label": "夜神 (默认62001)", "device_port": 62001},
    "custom": {"label": "自定义", "device_port": 5555},
}


class AdbConnectorPlugin(BasePlugin):
    name = "adb_connector"

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._client: AdbClient | None = None
        self._device: AdbDevice | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._stop_heartbeat = threading.Event()

        self.event_bus.on("request_adb_reconnect", self._on_request_reconnect)

    def init(self) -> None:
        self._init_client()

    def _init_client(self) -> None:
        host = self.config.get("host", "127.0.0.1")
        self._client = AdbClient(host=host, port=5037)
        logger.info(f"ADB 客户端初始化: {host}:5037")

    def start(self) -> None:
        self._running = True
        # 首次连接放到后台线程，避免阻塞 UI 启动
        threading.Thread(target=self._connect, daemon=True).start()
        self._start_heartbeat()

    def stop(self) -> None:
        self._running = False
        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=3)
        self._device = None

    def reconnect(self, new_config: dict[str, Any]) -> None:
        """热重连：断开当前连接，用新配置重新连接"""
        logger.info(f"热重连: {new_config}")
        self.stop()
        # 尝试关闭旧 ADB server，确保新路径生效
        try:
            if self._client:
                self._client.server_kill()
                logger.info("已关闭旧 ADB server")
        except Exception:
            pass
        self.config = new_config
        self._init_client()
        self._stop_heartbeat.clear()
        self.start()

    def _on_request_reconnect(self, _data=None) -> None:
        if not self._running:
            return
        logger.warning("收到重新连接 ADB 的请求，正在断开当前连接并重新建立连接...")
        self._device = None
        self.event_bus.emit("device_disconnected")
        # 异步执行连接，避免卡住
        threading.Thread(target=self._connect, daemon=True).start()

    def _connect(self) -> None:
        serial = self.config.get("device_serial")
        if not serial:
            # 从 host:port 构造设备序列号
            host = self.config.get("host", "127.0.0.1")
            port = self.config.get("port", 7555)
            serial = f"{host}:{port}"
        try:
            self._device = self._client.device(serial)
            info = self._device.shell("getprop ro.product.model").strip()
            logger.info(f"已连接设备: {self._device.serial} ({info})")
            self.event_bus.emit("device_connected", {"device": self._device})
        except Exception:
            logger.exception("ADB 连接失败")
            self._device = None
            self.event_bus.emit("device_disconnected")

    def test_connection(self, test_config: dict[str, Any] | None = None) -> dict[str, Any]:
        """测试连接，返回诊断信息"""
        cfg = test_config or self.config
        host = cfg.get("host", "127.0.0.1")
        port = cfg.get("port", 7555)
        serial = cfg.get("device_serial") or f"{host}:{port}"

        result = {
            "success": False,
            "model": "",
            "resolution": "",
            "adb_version": "",
            "latency_ms": 0,
            "serial": "",
            "error": "",
        }

        try:
            client = AdbClient(host=host, port=5037)

            # 测延迟
            t0 = time.perf_counter()
            server_version = client.server_version()
            result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            result["adb_version"] = str(server_version)

            device = client.device(serial)

            result["serial"] = device.serial
            result["model"] = device.shell("getprop ro.product.model").strip()

            # 获取分辨率
            wm_output = device.shell("wm size").strip()
            if ":" in wm_output:
                result["resolution"] = wm_output.split(":")[-1].strip()

            result["success"] = True
        except Exception as e:
            result["error"] = str(e)

        return result

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

    def get_debug_info(self) -> dict[str, Any]:
        return {
            "connected": self.is_connected,
            "device_serial": self._device.serial if self._device else None,
            "config_host": self.config.get("host", "127.0.0.1"),
            "config_port": self.config.get("port", 7555),
        }

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "host": {"type": "string", "default": "127.0.0.1", "label": "ADB 地址"},
            "port": {"type": "integer", "default": 7555, "label": "设备端口"},
            "device_serial": {"type": "string", "default": "", "label": "设备序列号（留空自动使用 host:port）"},
        }

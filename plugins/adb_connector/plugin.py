"""ADB connection plugin: connect, keep alive, reconnect, and diagnose devices."""

import logging
import threading
import time
from typing import Any, Callable, TypeVar

from adbutils import AdbClient, AdbDevice

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

T = TypeVar("T")

EMULATOR_PRESETS = {
    "mumu": {"label": "MuMu (默认7555)", "device_port": 7555},
    "leidian": {"label": "雷电 (默认5555)", "device_port": 5555},
    "yeshen": {"label": "夜神 (默认62001)", "device_port": 62001},
    "custom": {"label": "自定义", "device_port": 5555},
}


class AdbConnectorPlugin(BasePlugin):
    name = "adb_connector"

    HEARTBEAT_INTERVAL_SECONDS = 5.0
    CONNECT_TIMEOUT_SECONDS = 5.0
    CONNECT_RETRY_COUNT = 3

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._client: AdbClient | None = None
        self._device: AdbDevice | None = None
        self._device_serial: str | None = None

        self._connection_lock = threading.RLock()
        self._thread_lock = threading.Lock()
        self._connect_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._stop_heartbeat = threading.Event()

        self._last_connected_at: float | None = None
        self._last_heartbeat_at: float | None = None
        self._last_error = ""
        self._last_connect_result = ""
        self._heartbeat_ok = False
        self._reconnect_count = 0

        self.event_bus.on("request_adb_reconnect", self._on_request_reconnect)

    def init(self) -> None:
        self._init_client()

    def _init_client(self) -> None:
        server_host, server_port = self._get_adb_server_endpoint(self.config)
        self._client = AdbClient(
            host=server_host,
            port=server_port,
            socket_timeout=self.CONNECT_TIMEOUT_SECONDS,
        )
        logger.info("ADB client initialized: %s:%s", server_host, server_port)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_heartbeat.clear()
        self._schedule_connect("startup")
        self._start_heartbeat()

    def stop(self) -> None:
        self._running = False
        self._stop_heartbeat.set()

        if self._connect_thread and self._connect_thread.is_alive() and self._connect_thread is not threading.current_thread():
            self._connect_thread.join(timeout=3)
        if self._heartbeat_thread and self._heartbeat_thread.is_alive() and self._heartbeat_thread is not threading.current_thread():
            self._heartbeat_thread.join(timeout=3)

        self._mark_disconnected("plugin stopped", emit=True)

    def reconnect(self, new_config: dict[str, Any]) -> None:
        """Apply a new profile and reconnect without killing the global ADB server."""
        logger.info("ADB reconnect requested: %s", new_config)
        self.config = dict(new_config)
        with self._connection_lock:
            self._init_client()
            self._reconnect_count += 1
        self._mark_disconnected("config changed", emit=True)

        if not self._running:
            self.start()
            return
        self._schedule_connect("config changed")

    def _on_request_reconnect(self, _data=None) -> None:
        if not self._running:
            return
        logger.warning("ADB reconnect requested by another plugin")
        with self._connection_lock:
            self._reconnect_count += 1
        self._mark_disconnected("reconnect requested", emit=True)
        self._schedule_connect("reconnect requested")

    def _schedule_connect(self, reason: str) -> None:
        if not self._running:
            return

        with self._thread_lock:
            if self._connect_thread and self._connect_thread.is_alive():
                logger.debug("ADB connect already running, skip duplicate request: %s", reason)
                return
            self._connect_thread = threading.Thread(
                target=self._connect_worker,
                args=(reason,),
                daemon=True,
                name="adb-connect",
            )
            self._connect_thread.start()

    def _connect_worker(self, reason: str) -> None:
        for attempt in range(1, self.CONNECT_RETRY_COUNT + 1):
            if self._stop_heartbeat.is_set() or not self._running:
                return
            if self._connect_once(reason, attempt):
                return
            if attempt < self.CONNECT_RETRY_COUNT:
                delay = min(1.5 * attempt, 5.0)
                self._stop_heartbeat.wait(timeout=delay)

    def _connect_once(self, reason: str, attempt: int) -> bool:
        cfg = dict(self.config)
        serial = self._get_target_serial(cfg)
        connect_result = ""

        try:
            with self._connection_lock:
                if self._client is None:
                    self._init_client()
                if self._client is None:
                    raise RuntimeError("ADB client is not initialized")

                server_version = self._client.server_version()
                if self._is_tcp_serial(serial):
                    connect_result = self._client.connect(serial, timeout=self.CONNECT_TIMEOUT_SECONDS)

                device = self._client.device(serial)
                model = device.shell("getprop ro.product.model").strip()
                wm_size = device.shell("wm size").strip()
                if self._stop_heartbeat.is_set() or not self._running:
                    return False

                self._device = device
                self._device_serial = device.serial
                self._last_connected_at = time.time()
                self._last_heartbeat_at = self._last_connected_at
                self._last_error = ""
                self._last_connect_result = connect_result
                self._heartbeat_ok = True

                payload = {
                    "device": device,
                    "connector": self,
                    "serial": device.serial,
                    "model": model,
                    "resolution": self._parse_wm_size(wm_size),
                    "adb_version": str(server_version),
                    "connect_result": connect_result,
                }

            logger.info(
                "ADB connected: serial=%s model=%s reason=%s attempt=%s result=%s",
                payload["serial"],
                model,
                reason,
                attempt,
                connect_result or "transport ready",
            )
            self.event_bus.emit("device_connected", payload)
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning(
                "ADB connect failed: serial=%s reason=%s attempt=%s/%s error=%s",
                serial,
                reason,
                attempt,
                self.CONNECT_RETRY_COUNT,
                exc,
            )
            self._mark_disconnected(str(exc), emit=True)
            return False

    def test_connection(self, test_config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Test a profile and return diagnostic information."""
        cfg = test_config or self.config
        server_host, server_port = self._get_adb_server_endpoint(cfg)
        serial = self._get_target_serial(cfg)

        result = {
            "success": False,
            "model": "",
            "resolution": "",
            "adb_version": "",
            "latency_ms": 0,
            "serial": serial,
            "error": "",
            "connect_result": "",
            "devices": [],
            "adb_server": f"{server_host}:{server_port}",
        }

        try:
            client = AdbClient(
                host=server_host,
                port=server_port,
                socket_timeout=self.CONNECT_TIMEOUT_SECONDS,
            )

            t0 = time.perf_counter()
            server_version = client.server_version()
            result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            result["adb_version"] = str(server_version)

            if self._is_tcp_serial(serial):
                result["connect_result"] = client.connect(serial, timeout=self.CONNECT_TIMEOUT_SECONDS)

            result["devices"] = [device.serial for device in client.device_list()]
            device = client.device(serial)
            result["serial"] = device.serial
            result["model"] = device.shell("getprop ro.product.model").strip()
            result["resolution"] = self._parse_wm_size(device.shell("wm size").strip())
            result["success"] = True
        except Exception as exc:
            result["error"] = str(exc)

        return result

    def _start_heartbeat(self) -> None:
        with self._thread_lock:
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                return
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name="adb-heartbeat",
            )
            self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop_heartbeat.wait(timeout=self.HEARTBEAT_INTERVAL_SECONDS):
            if not self._running:
                return

            if not self.is_connected:
                self._schedule_connect("heartbeat")
                continue

            try:
                self.shell("echo ok")
                with self._connection_lock:
                    self._last_heartbeat_at = time.time()
                    self._heartbeat_ok = True
            except Exception as exc:
                logger.warning("ADB heartbeat failed: %s", exc)

    def shell(self, command: str) -> str:
        """Run a shell command through the current device with serialized ADB access."""
        return self._run_on_device(lambda device: device.shell(command))

    def screenshot(self):
        """Capture a screenshot through the current device with serialized ADB access."""
        return self._run_on_device(lambda device: device.screenshot())

    def _run_on_device(self, operation: Callable[[AdbDevice], T]) -> T:
        error: Exception | None = None
        with self._connection_lock:
            device = self._device
            if device is None:
                raise RuntimeError("ADB device is not connected")
            try:
                return operation(device)
            except Exception as exc:
                error = exc

        if error is not None:
            self._handle_device_error(error)
            raise error

        raise RuntimeError("ADB operation failed without an exception")

    def _handle_device_error(self, error: Exception) -> None:
        logger.warning("ADB device operation failed, scheduling reconnect: %s", error)
        with self._connection_lock:
            self._reconnect_count += 1
        self._mark_disconnected(str(error), emit=True)
        self._schedule_connect("device operation failed")

    def _mark_disconnected(self, error: str = "", emit: bool = False) -> None:
        with self._connection_lock:
            was_connected = self._device is not None
            self._device = None
            self._device_serial = None
            self._heartbeat_ok = False
            if error:
                self._last_error = error

        if emit and was_connected:
            self.event_bus.emit("device_disconnected", {"error": error})

    @staticmethod
    def _get_adb_server_endpoint(config: dict[str, Any]) -> tuple[str, int]:
        host = config.get("adb_server_host") or config.get("server_host") or "127.0.0.1"
        port = config.get("adb_server_port") or config.get("server_port") or 5037
        return str(host).strip(), int(port)

    @staticmethod
    def _get_target_serial(config: dict[str, Any]) -> str:
        serial = config.get("device_serial")
        if serial:
            return str(serial).strip()

        host = str(config.get("host", "127.0.0.1")).strip() or "127.0.0.1"
        port = int(config.get("port", 7555))
        return f"{host}:{port}"

    @staticmethod
    def _is_tcp_serial(serial: str) -> bool:
        return ":" in serial and not serial.startswith("emulator-")

    @staticmethod
    def _parse_wm_size(wm_output: str) -> str:
        if ":" in wm_output:
            return wm_output.split(":", 1)[1].strip()
        return wm_output.strip()

    @property
    def device(self) -> AdbDevice | None:
        with self._connection_lock:
            return self._device

    @property
    def is_connected(self) -> bool:
        with self._connection_lock:
            return self._device is not None

    def get_debug_info(self) -> dict[str, Any]:
        with self._connection_lock:
            return {
                "connected": self._device is not None,
                "device_serial": self._device_serial,
                "target_serial": self._get_target_serial(self.config),
                "adb_server": ":".join(map(str, self._get_adb_server_endpoint(self.config))),
                "heartbeat_ok": self._heartbeat_ok,
                "last_connected_at": self._last_connected_at,
                "last_heartbeat_at": self._last_heartbeat_at,
                "last_error": self._last_error,
                "last_connect_result": self._last_connect_result,
                "reconnect_count": self._reconnect_count,
                "connect_thread_alive": self._connect_thread.is_alive() if self._connect_thread else False,
                "heartbeat_thread_alive": self._heartbeat_thread.is_alive() if self._heartbeat_thread else False,
            }

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "host": {"type": "string", "default": "127.0.0.1", "label": "ADB 地址"},
            "port": {"type": "integer", "default": 7555, "label": "设备端口"},
            "device_serial": {"type": "string", "default": "", "label": "设备序列号（留空自动使用 host:port）"},
        }

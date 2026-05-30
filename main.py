"""金铲铲智能助手 — 主入口"""

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_manager import ConfigManager
from core.event_bus import EventBus
from core.plugin_manager import PluginManager
from plugins.adb_connector.plugin import AdbConnectorPlugin
from plugins.screenshot.plugin import ScreenshotPlugin
from plugins.recognizer.plugin import RecognizerPlugin
from plugins.decision_engine.plugin import DecisionEnginePlugin
from plugins.action_executor.plugin import ActionExecutorPlugin
from ui.app import App


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("金铲铲智能助手启动中...")

    config_mgr = ConfigManager()

    # 根据配置决定是否启用调试模式
    debug_enabled = config_mgr.get("debug.enabled", False)
    debug_manager = None

    if debug_enabled:
        from core.debug_event_bus import DebugEventBus
        from core.debug_manager import DebugManager
        event_bus = DebugEventBus()
        logger.info("调试模式已开启，使用 DebugEventBus")
    else:
        event_bus = EventBus()

    # 应用用户自定义 ADB 路径（留空则使用 adbutils 内置 ADB）
    adb_path = config_mgr.get_adb_path()
    if adb_path and os.path.isfile(adb_path):
        os.environ["ADBUTILS_ADB_PATH"] = adb_path
        logger.info(f"使用自定义 ADB 路径: {adb_path}")

    plugin_mgr = PluginManager(event_bus, config_mgr.data)

    # ADB 插件使用活跃 profile 的配置
    adb_config = config_mgr.get_active_adb_profile()
    plugin_mgr.register(AdbConnectorPlugin, adb_config)

    plugin_mgr.register(ScreenshotPlugin, config_mgr.get("screenshot", {}))
    plugin_mgr.register(RecognizerPlugin, {
        "season": config_mgr.season,
        "emulator_width": config_mgr.get("emulator.width", 1280),
        "emulator_height": config_mgr.get("emulator.height", 720),
        "debug": config_mgr.get("recognizer.debug", False),
        "use_gpu": config_mgr.get("recognizer.use_gpu", True),
    })
    plugin_mgr.register(DecisionEnginePlugin, config_mgr.get("automation", {}))
    plugin_mgr.register(ActionExecutorPlugin, {
        "emulator_width": config_mgr.get("emulator.width", 1280),
        "emulator_height": config_mgr.get("emulator.height", 720),
    })

    plugin_mgr.init_all()

    # 先创建 UI，再启动插件，避免 ADB 连接阻塞导致窗口出不来
    if debug_enabled:
        debug_manager = DebugManager(event_bus, plugin_mgr)

    app = App(event_bus, config_mgr.data, config_mgr, debug_manager)

    adb_plugin = plugin_mgr.get("adb_connector")
    if app.settings_page and adb_plugin:
        app.settings_page.set_adb_plugin(adb_plugin)

    plugin_mgr.start_all()

    def on_closing():
        plugin_mgr.stop_all()

    event_bus.on("app_closing", on_closing)

    logger.info("UI 已启动")
    app.mainloop()


if __name__ == "__main__":
    main()

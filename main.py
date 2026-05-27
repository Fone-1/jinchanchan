"""金铲铲智能助手 — 主入口"""

import logging
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
    event_bus = EventBus()
    plugin_mgr = PluginManager(event_bus, config_mgr.data)

    # ADB 插件使用活跃 profile 的配置
    adb_config = config_mgr.get_active_adb_profile()
    plugin_mgr.register(AdbConnectorPlugin, adb_config)

    plugin_mgr.register(ScreenshotPlugin, config_mgr.get("screenshot", {}))
    plugin_mgr.register(RecognizerPlugin, {
        "season": config_mgr.season,
        "emulator_width": config_mgr.get("emulator.width", 1280),
        "emulator_height": config_mgr.get("emulator.height", 720),
    })
    plugin_mgr.register(DecisionEnginePlugin, config_mgr.get("automation", {}))
    plugin_mgr.register(ActionExecutorPlugin, {
        "emulator_width": config_mgr.get("emulator.width", 1280),
        "emulator_height": config_mgr.get("emulator.height", 720),
    })

    plugin_mgr.init_all()
    plugin_mgr.start_all()

    app = App(event_bus, config_mgr.data, config_mgr)

    # 将 ADB 插件引用传给设置页
    adb_plugin = plugin_mgr.get("adb_connector")
    if app.settings_page and adb_plugin:
        app.settings_page.set_adb_plugin(adb_plugin)

    def on_closing():
        plugin_mgr.stop_all()

    event_bus.on("app_closing", on_closing)

    logger.info("UI 已启动")
    app.mainloop()


if __name__ == "__main__":
    main()

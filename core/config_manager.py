"""配置中心 — 统一管理全局配置和插件配置"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


class ConfigManager:
    def __init__(self, config_path: str | Path | None = None):
        self._path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
            logger.info(f"配置已加载: {self._path}")
        else:
            logger.warning(f"配置文件不存在，使用空配置: {self._path}")
            self._data = {}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, allow_unicode=True, default_flow_style=False)

    def get(self, key: str, default: Any = None) -> Any:
        """点分路径获取配置，如 'adb.host'"""
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
            if val is None:
                return default
        return val

    def set(self, key: str, value: Any) -> None:
        """点分路径设置配置"""
        keys = key.split(".")
        d = self._data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def season(self) -> str:
        return self.get("season.current", "s18_mode17")

    def set_season(self, dir_name: str) -> None:
        self.set("season.current", dir_name)
        self.save()

    # --- ADB 路径管理 ---

    def get_adb_path(self) -> str:
        """获取用户配置的 ADB 路径，留空表示使用内置 ADB"""
        return self.get("adb.path", "")

    def set_adb_path(self, path: str) -> None:
        self.set("adb.path", path)
        self.save()

    # --- ADB Profile 管理 ---

    def get_adb_profiles(self) -> list[dict[str, Any]]:
        return self.get("adb.profiles", [])

    def get_active_adb_profile(self) -> dict[str, Any]:
        name = self.get("adb.active_profile", "")
        for p in self.get_adb_profiles():
            if p.get("name") == name:
                return p
        profiles = self.get_adb_profiles()
        return profiles[0] if profiles else {}

    def set_active_adb_profile(self, name: str) -> None:
        self.set("adb.active_profile", name)

    def save_adb_profile(self, profile: dict[str, Any]) -> None:
        profiles = self.get_adb_profiles()
        for i, p in enumerate(profiles):
            if p.get("name") == profile.get("name"):
                profiles[i] = profile
                self.save()
                return
        profiles.append(profile)
        self.set("adb.profiles", profiles)
        self.save()

    def delete_adb_profile(self, name: str) -> None:
        profiles = [p for p in self.get_adb_profiles() if p.get("name") != name]
        self.set("adb.profiles", profiles)
        if self.get("adb.active_profile") == name and profiles:
            self.set("adb.active_profile", profiles[0].get("name", ""))
        self.save()

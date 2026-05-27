"""远程数据拉取（腾讯 CDN）"""

import json
import urllib.request

from ._constants import BASE_URL


def fetch_js_json(url: str) -> dict:
    with urllib.request.urlopen(url) as resp:
        raw = resp.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gbk")
    return json.loads(text)


def get_version_config() -> list[dict]:
    return fetch_js_json(f"{BASE_URL}/config/versiondataconfig.js")


def list_all_modes(config: list[dict] | None = None) -> list[dict]:
    """列出所有可用的 mode+season 组合"""
    if config is None:
        config = get_version_config()
    modes = {}
    for c in config:
        key = (c.get("mode"), c.get("season"))
        ver = c.get("version", "")
        existing = modes.get(key)
        if not existing or c.get("is_newest_version") == 1 or ver > existing.get("version", ""):
            modes[key] = {
                "mode": c.get("mode"),
                "season": c.get("season"),
                "name": c.get("name", ""),
                "version": ver,
                "is_newest": c.get("is_newest_version") == 1,
                "dir_name": f"{c.get('season', '').lower()}_mode{c.get('mode')}",
                "herourl": c.get("herourl", ""),
                "traiturl": c.get("traiturl", ""),
                "equipurl": c.get("equipurl", ""),
                "raceurl": c.get("raceurl", ""),
                "joburl": c.get("joburl", ""),
            }
    result = sorted(modes.values(), key=lambda m: (m["season"], m["mode"]), reverse=True)
    return result

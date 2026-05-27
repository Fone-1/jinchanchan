"""金铲铲之战官方数据拉取模块"""

import json
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://game.gtimg.cn/images/lol/act/jkzlk/js"
DATA_DIR = Path(__file__).parent


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


def find_mode(modes: list[dict], mode: str, season: str) -> dict | None:
    for m in modes:
        if m["mode"] == mode and m["season"] == season:
            return m
    return None


def _build_id_name_map(raw_data: dict) -> dict[str, str]:
    return {str(rid): r.get("name", "") for rid, r in raw_data.get("data", {}).items()}


def convert_chess(raw_data: dict, race_map: dict, job_map: dict) -> dict:
    result = {}
    for hid, h in raw_data.get("data", {}).items():
        name = h.get("name", "")
        if not name or h.get("price", "0") == "0":
            continue
        species_id = str(h.get("species", ""))
        class_id = str(h.get("class", ""))
        pic_url = h.get("picture", "")
        result[name] = {
            "id": hid,
            "cost": int(h.get("price", 0)),
            "race": race_map.get(species_id, ""),
            "job": job_map.get(class_id, ""),
            "icon": pic_url.split("/")[-1] if pic_url else "",
            "icon_url": pic_url,
            "hp": int(h.get("initHP", 0)),
            "attack": int(h.get("initAttackDamage", 0)),
            "armor": int(h.get("armor", 0)),
            "magic_resist": int(h.get("magicResist", 0)),
            "attack_speed": float(h.get("attackSpeed", 0)),
            "attack_range": int(h.get("attackRange", 0)),
            "skill_name": h.get("skillName", ""),
            "skill_desc": h.get("skillDesc", ""),
            "skill_icon": h.get("skillIcon", ""),
        }
    return result


def convert_traits(raw_data: dict) -> dict:
    result = {}
    for tid, t in raw_data.get("data", {}).items():
        name = t.get("name", "")
        if not name:
            continue
        num_list = t.get("numList", "")
        thresholds = [int(x) for x in num_list.split("|") if x.isdigit()] if num_list else []
        if name not in result:
            result[name] = {
                "id": tid, "type": t.get("type", 0),
                "thresholds": thresholds, "picture": t.get("picture", ""),
                "desc": t.get("desc2", ""),
            }
        else:
            existing = result[name]
            for th in thresholds:
                if th not in existing["thresholds"]:
                    existing["thresholds"].extend(thresholds)
                    existing["thresholds"].sort()
                    break
    return result


def convert_equips(raw_data: dict) -> dict:
    result = {}
    for eid, e in raw_data.get("data", {}).items():
        name = e.get("name", "")
        if not name:
            continue
        result[name] = {
            "id": eid, "type": e.get("type", ""),
            "desc": e.get("desc", ""), "picture": e.get("picture", ""),
        }
    return result


def _save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_mode_data(mode_info: dict, progress_cb=None) -> dict[str, int]:
    """拉取指定模式的全部数据并保存到本地

    Args:
        mode_info: list_all_modes 返回的模式信息字典
        progress_cb: 可选的进度回调 (step, total, message)

    Returns:
        各数据文件的条目数 {"champions": N, "traits": N, ...}
    """
    total_steps = 5
    step = 0

    def progress(msg):
        nonlocal step
        step += 1
        if progress_cb:
            progress_cb(step, total_steps, msg)

    progress("拉取种族/职业映射...")
    race_raw = fetch_js_json(f"{BASE_URL}{mode_info['raceurl']}")
    job_raw = fetch_js_json(f"{BASE_URL}{mode_info['joburl']}")
    race_map = _build_id_name_map(race_raw)
    job_map = _build_id_name_map(job_raw)

    progress("拉取弈子数据...")
    chess_raw = fetch_js_json(f"{BASE_URL}{mode_info['herourl']}")
    chess = convert_chess(chess_raw, race_map, job_map)

    progress("拉取羁绊数据...")
    trait_raw = fetch_js_json(f"{BASE_URL}{mode_info['traiturl']}")
    traits = convert_traits(trait_raw)

    progress("拉取装备数据...")
    equip_raw = fetch_js_json(f"{BASE_URL}{mode_info['equipurl']}")
    equips = convert_equips(equip_raw)

    progress("保存数据...")
    season_dir = DATA_DIR / mode_info["dir_name"]
    _save_json(season_dir / "champions.json", chess)
    _save_json(season_dir / "traits.json", traits)
    _save_json(season_dir / "items.json", equips)

    pool = {"pool_size": {1: 22, 2: 20, 3: 17, 4: 10, 5: 9}, "champions": {}}
    for name, info in chess.items():
        pool["champions"][name] = {"cost": info["cost"], "copies": pool["pool_size"].get(info["cost"], 0)}
    _save_json(season_dir / "pool.json", pool)

    comps_path = season_dir / "comps.json"
    if not comps_path.exists():
        _save_json(comps_path, {})

    # 保存版本信息
    meta = {"version": mode_info["version"], "mode": mode_info["mode"],
            "season": mode_info["season"], "name": mode_info["name"]}
    _save_json(season_dir / "_meta.json", meta)

    return {
        "champions": len(chess),
        "traits": len(traits),
        "items": len(equips),
    }


def get_local_modes() -> list[dict]:
    """扫描本地已下载的模式数据"""
    result = []
    for d in sorted(DATA_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name.startswith("."):
            continue
        meta_path = d / "_meta.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta["dir_name"] = d.name
            # 统计数据条目数
            for key in ["champions", "traits", "items"]:
                fp = d / f"{key}.json"
                if fp.exists():
                    with open(fp, "r", encoding="utf-8") as f:
                        meta[f"{key}_count"] = len(json.load(f))
            result.append(meta)
    return result


def delete_mode(dir_name: str) -> bool:
    """删除本地模式数据目录"""
    import shutil
    target = DATA_DIR / dir_name
    if not target.exists() or not target.is_dir():
        return False
    # 安全检查：只删除包含 _meta.json 的目录
    if not (target / "_meta.json").exists():
        return False
    shutil.rmtree(target)
    return True

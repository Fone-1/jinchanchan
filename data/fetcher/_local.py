"""本地数据管理与拉取编排"""

import json
import shutil
from pathlib import Path

from ._constants import BASE_URL, DATA_DIR
from ._remote import fetch_js_json
from ._convert import _build_id_name_map, convert_chess, convert_traits, convert_equips


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
    target = DATA_DIR / dir_name
    if not target.exists() or not target.is_dir():
        return False
    # 安全检查：只删除包含 _meta.json 的目录
    if not (target / "_meta.json").exists():
        return False
    shutil.rmtree(target)
    return True

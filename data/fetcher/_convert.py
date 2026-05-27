"""原始数据格式转换（纯函数）"""


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

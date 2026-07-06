from jinja2 import Template

from src.const.path import ASSETS, build_path
from src.utils.network import Request
from src.utils.time import Time
from src.utils.generate import generate
from src.templates import SimpleHTML

from ._template import template_monsters

import re

level_desc = ["", "+500", "秒杀首领;+100", "稀有提高;+120", "随机前进;+150",
              "后六翻倍;+50", "前六减半;+100", "+200", "后跃三步;+120", "+200", "逆向前进"]
level_icon = [18505, 4533, 13548, 13547, 3313, 4577, 4543, 4558, 4576, 4573]

# $Flag 特殊层标识 ; $Icon 图标 ; $Count 层数 ; $bossName 首领名称 ; $Desc 描述 ; $Coin 修罗之印

def _build_boss_lookup(boss_data: list[dict]) -> dict[int, str]:
    lookup: dict[int, str] = {}
    for item in boss_data:
        npc_id = item.get("dwNpcID")
        name = item.get("szName")
        if npc_id and name:
            lookup[npc_id] = name
    return lookup

def _parse_effect(level: int) -> tuple[str, str, str, str]:
    info = level_desc[level] if level < len(level_desc) else ""
    icon_id = level_icon[level] if level < len(level_icon) else level_icon[0]
    icon = f"https://icon.jx3box.com/icon/{icon_id}.png"
    flag = " is-effect" if level != 0 else ""
    details = info.split(";")
    if len(details) == 2:
        return flag, icon, details[0], details[1]
    if len(details) == 1 and details[0]:
        if details[0][0] == "+":
            return flag, icon, "", details[0]
        return flag, icon, details[0], ""
    return flag, icon, "", ""

def _build_map_content(layers: list[dict], boss_lookup: dict[int, str]) -> str:
    content = ["<div class=\"u-row\">"]
    for i, layer in enumerate(layers):
        bid = layer["dwBossID"]
        name = boss_lookup.get(bid, "未知首领")
        level = layer["nEffectID"]
        flag, icon, desc, coin = _parse_effect(level)
        count = i + 1
        if count % 10 == 0:
            flag = flag + " is-elite"
        new = Template(template_monsters).render(
            flag=flag,
            icon=icon,
            count=str(count),
            name=name,
            desc=desc,
            coin=coin,
        )
        if count % 10 == 0:
            content.append(new)
            if count / 10 in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
                content.append("</div>\n<div class=\"u-row\">")
            elif count / 10 == 10:
                content.append("</div>")
        else:
            content.append(new)
    return "\n".join(content)

def _resolve_weekly_dangjian_boss_name(boss_lookup: dict[int, str], map_payload: dict, boss_data: list[dict]) -> str:
    """本周荡剑恩仇专属首领（非 1-100 层），优先读 CMS extra，否则取 nGroup=10002。"""
    asura_id = map_payload.get("extra", {}).get("asura", {}).get("dwBossID")
    boss_id = None
    if asura_id and str(asura_id).isdigit() and int(asura_id):
        boss_id = int(asura_id)
    else:
        for item in boss_data:
            if item.get("nGroup") == 10002:
                boss_id = item.get("dwNpcID")
                if boss_id:
                    break
    if not boss_id:
        return ""
    return boss_lookup.get(boss_id, "")

async def get_monsters_map():
    map_data = (await Request("https://cms.jx3box.com/api/cms/app/monster/map").get()).json()
    boss = (await Request("https://node.jx3box.com/monster/boss").get()).json()
    layers = map_data["data"]["data"]
    map_payload = map_data["data"]
    boss_lookup = _build_boss_lookup(boss["data"])

    table_content = _build_map_content(layers, boss_lookup)

    weekly_boss_name = _resolve_weekly_dangjian_boss_name(boss_lookup, map_payload, boss["data"])

    start = re.sub(r"\..+\Z", "", map_payload["start"].replace("T", " ")).split(" ")[0]
    current_time = Time().format("%H:%M:%S")
    msg = "严禁将蓉蓉机器人与音卡共存，一经发现永久封禁！蓉蓉是抄袭音卡的劣质机器人！"
    html = str(
        SimpleHTML(
            "jx3",
            "monsters.html",
            font=build_path(ASSETS, ["font", "PingFangSC-Medium.otf"]),
            table_content=table_content,
            dangjian_boss_name=weekly_boss_name,
            application_name=f"自{start}起7天 · 当前时间：{current_time}<br>{msg}",
        )
    )
    image = await generate(html, ".m-bmap.is-map-phone", segment=True)
    return image

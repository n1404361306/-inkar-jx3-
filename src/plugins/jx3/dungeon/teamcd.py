from jinja2 import Template
from itertools import chain
from typing import Any
from collections import Counter

from src.config import Config
from src.const.jx3.school import School
from src.const.prompts import PROMPT
from src.const.path import ASSETS, build_path
from src.utils.database import db
from src.utils.database.classes import PersonalSettings, RoleData
from src.utils.database.player import search_player
from src.utils.tuilan import generate_timestamp, generate_dungeon_sign
from src.utils.generate import generate
from src.utils.network import Request
from src.templates import HTMLSourceCode, SimpleHTML, get_saohua

from ._template import (
    image_template,
    template_zone_record,
    table_zone_record_head
)

_EMPTY_TEAMCD_MSG = "该玩家目前尚未打过任何副本哦~\n注意：10人普通副本会在周五刷新一次。"


def _teamcd_entries(raw: dict | None) -> tuple[list[dict] | None, str | None]:
    if not isinstance(raw, dict):
        return None, "副本记录接口返回异常，请稍后再试！"
    code = raw.get("code")
    if code not in (0, 200):
        msg = str(raw.get("msg") or "未知错误")
        if "signature" in msg.lower() or "sign" in msg.lower():
            return None, "副本记录接口签名失败，请联系 Bot 管理员配置 sign_secret。"
        return None, f"副本记录查询失败：{msg}"
    entries = raw.get("data")
    if entries is None:
        return None, "副本记录接口未返回数据，请稍后再试！"
    if not isinstance(entries, list):
        return None, "副本记录接口返回格式异常，请稍后再试！"
    return entries, None


def _boss_progress(entry: dict) -> list[dict]:
    progress = entry.get("bossProgress")
    return progress if isinstance(progress, list) else []

def sort_role_data(objects: list[RoleData]) -> list[RoleData]:
    server_counts = Counter(obj.serverName for obj in objects)
    return sorted(objects, key=lambda obj: server_counts[obj.serverName], reverse=True)

def build_teamcd_request(guid: str) -> Request:
    ts = generate_timestamp()
    params = {
        "globalRoleId": guid,
        "sign": generate_dungeon_sign(f"globalRoleId={guid}&ts={ts}"),
        "ts": ts
    }
    return Request("https://m.pvp.xoyo.com/h5/parser/cd-process/get-by-role", params=params)

async def get_zone_record_image(server: str, role: str):
    role_info = await search_player(role_name=role, server_name=server)
    guid = role_info.globalRoleId
    if guid == "":
        return PROMPT.PlayerNotExist
    request = build_teamcd_request(guid)
    raw = (await request.post(tuilan=True)).json()
    entries, error = _teamcd_entries(raw)
    if error:
        return error
    if not entries:
        return _EMPTY_TEAMCD_MSG
    unable = Template(image_template).render(
        image_path = build_path(ASSETS, ["image", "jx3", "cat", "grey.png"])
    )
    available = Template(image_template).render(
        image_path = build_path(ASSETS, ["image", "jx3", "cat", "gold.png"])
    )
    contents = []
    for i in entries:
        images = []
        map_name = i["mapName"]
        map_type = i["mapType"]
        for x in _boss_progress(i):
            if x["finished"] is True:
                images.append(unable)
            else:
                images.append(available)
        image_content = "\n".join(images)
        contents.append(
            Template(template_zone_record).render(
                zone_name = map_name,
                zone_mode = map_type,
                images = image_content
            )
        )
    html = str(
        HTMLSourceCode(
            application_name = f"副本记录 · [{role}·{server}]",
            table_head = table_zone_record_head,
            table_body = "\n".join(contents)
        )
    )
    image = await generate(html, ".container", segment=True)
    return image
    
def parse_data(data) -> dict:
    entries, error = _teamcd_entries(data)
    if error or not entries:
        return {}
    result = {}
    for entry in entries:
        map_type = entry["mapType"]
        map_name = entry["mapName"]
        progress_finished = [boss["finished"] for boss in _boss_progress(entry)]
        key = f"{map_type}{map_name}"
        result[key] = progress_finished
    return result

def synchronize_keys(data: list[list[dict[str, list[bool]]]]) -> list[list[dict[str, list[bool]]]]:
    all_keys = set(k for sublist in data for d in sublist for k in d.keys())
    for sublist in data:
        current_keys: set[str] = set(k for d in sublist for k in d.keys())
        missing_keys: set[str] = all_keys - current_keys
        for key in missing_keys:
            value_length = max(len(d[key]) for sublist_inner in data for d in sublist_inner if key in d)
            for d in sublist:
                if key not in d:
                    d[key] = [False] * value_length
    return data

    
async def get_mulit_record_image(server: str, roles: list[str]):
    not_found_roles: list[str] = []
    found_roles: list[str] = []
    for each_role in roles:
        role_data = await search_player(
            role_name = each_role,
            server_name = server,
            local_lookup = True
        )
        guid = role_data.globalRoleId
        if guid == "":
            not_found_roles.append(each_role)
        else:
            found_roles.append(guid)
    if len(not_found_roles) > 0:
        return "有以下角色尚未存在于音卡的数据库中，请提交角色！\n" + "\n".join(not_found_roles)
    responses = [
        (await request.post(tuilan=True)).json()
        for request
        in [
            build_teamcd_request(each_guid)
            for each_guid
            in found_roles
        ]
    ]
    roles_data: list[list[dict[str, list[bool]]]] = [[] for _ in range(len(found_roles))]
    num = 0
    api_error: str | None = None
    for each_response in responses:
        _, error = _teamcd_entries(each_response)
        if error and api_error is None:
            api_error = error
        roles_data[num].append(parse_data(each_response))
        num += 1
    final_data = synchronize_keys(roles_data)
    zones: list[str] = list(set(chain.from_iterable(d.keys() for sublist in final_data for d in sublist)))
    if not zones:
        return api_error or _EMPTY_TEAMCD_MSG
    table_head = "<tr><th class=\"short-column\">角色</th>" + "\n".join([f"<th class=\"short-column\">{zone}</th>" for zone in zones]) + "</tr>"
    tables: list[str] = []
    num = 0
    for each_role_data in roles_data:
        data = each_role_data[0]
        row = ["<td class=\"short-column\">" + roles[num] + "</td>"]
        for each_zone in zones:
            progress = data[each_zone]
            image = "\n".join(["<img src=\"" + build_path(ASSETS, ["image", "jx3", "cat", "gold.png" if not value else "grey.png"]) + "\" height=\"20\" width=\"20\">" for value in progress])
            row.append("<td class=\"short-column\">" + image + "</td>")
        tables.append(
            "<tr>\n" + "\n".join(row) + "\n</tr>"
        )
        num += 1
    html = str(
            HTMLSourceCode(
                application_name = "副本记录 · 多角色",
                table_head = table_head,
                table_body = "\n".join(tables)
            )
        )
    image = await generate(html, ".container", segment=True)
    return image

async def get_personal_roles_teamcd_image(user_id: int, keyword: str = ""):
    personal_settings: PersonalSettings | Any = db.where_one(PersonalSettings(), "user_id = ?", str(user_id), default=None)
    if personal_settings is None:
        return "您尚未绑定任何角色！请绑定后再尝试查询！"
    roles = sort_role_data(personal_settings.roles)
    responses = [
        (await request.post(tuilan=True)).json()
        for request
        in [
            build_teamcd_request(r.globalRoleId)
            for r
            in roles
        ]
    ]
    roles_data: list[list[dict[str, list[bool]]]] = [[] for _ in range(len(roles))]
    num = 0
    api_error: str | None = None
    for each_response in responses:
        _, error = _teamcd_entries(each_response)
        if error and api_error is None:
            api_error = error
        roles_data[num].append(parse_data(each_response))
        num += 1
    final_data = synchronize_keys(roles_data)
    zones: list[str] = list(set(chain.from_iterable(d.keys() for sublist in final_data for d in sublist)))
    zones = [z for z in zones if keyword in z]
    if len(zones) == 0:
        if api_error:
            return api_error
        return "未找到相关副本，请检查后重试！\n可能是当前所有绑定账号均未产生相关副本的记录，待至少一个角色通关其中一个首领后将产生记录。"
    width = 730 + len(zones) * 200
    zones = [z.lstrip("10人普通") for z in zones]
    table_head = "<tr><th style=\"width: 160px\">服务器</th><th style=\"width: 240px\">角色</th><th style=\"width: 160px\">门派</th>" + "\n".join([f"<th>{zone}</th>" for zone in zones]) + "</tr>"
    tables: list[str] = []
    num = 0
    for each_role_data in roles_data:
        data = each_role_data[0]
        row = [
            "<td><span class=\"server-tag\">" \
            + roles[num].serverName \
            + "</span></td><td><span style=\"display: inline-block;padding: 2px 8px;border-radius: 12px;background: " \
            + (School(roles[num].forceName).color or "") \
            + ";color: " \
            + "#FFFFFF" \
            + ";font-size: 24px;\">" \
            + roles[num].roleName + "</span></td>" \
            + "<td><span style=\"display: inline-block;padding: 2px 8px;border-radius: 12px;background: " \
            + (School(roles[num].forceName).color or "") \
            + ";color: " \
            + "#FFFFFF" \
            + ";font-size: 24px;\">" \
            + roles[num].forceName \
            + "</span></td>"
        ]
        for each_zone in zones:
            if each_zone not in data:
                each_zone = "10人普通" + each_zone
            progress = data[each_zone]
            image = "\n".join(["<img src=\"" + build_path(ASSETS, ["image", "jx3", "cat", "gold.png" if not value else "grey.png"]) + "\" height=\"20\" width=\"20\">" for value in progress])
            row.append("<td>" + image + "</td>")
        tables.append(
            "<tr>\n" + "\n".join(row) + "\n</tr>"
        )
        num += 1
    html = str(
        SimpleHTML(
            html_type = "jx3",
            html_template = "teamcd",
            width = width,
            app_info = "所有角色副本记录",
            font = build_path(ASSETS, ["font", "PingFangSC-Medium.otf"]),
            bot_name = Config.bot_basic.bot_name_argument,
            footer_msg = get_saohua(),
            table_head = table_head,
            table_body = "\n".join(tables)
        )
    )
    image = await generate(html, ".container", segment=True)
    return image
from jinja2 import Template

from src.config import Config
from src.utils.decorators import token_required
from src.utils.network import Request
from src.utils.time import Time
from src.utils.generate import generate
from src.templates import HTMLSourceCode

from ._template import template_interserver, template_local, table_recruit_head
from .parse import (
    Expr,
    format_expr_label,
    matches_expr,
    parse_recruit_query,
    pick_api_keywords,
    recruit_identity,
)


async def check_ad(msg: str, data: dict) -> bool:
    data = data["data"]
    for x in data:
        status = []
        for num in range(len(x)):
            status.append(True)
        result = []
        for y in x:
            if msg.find(y) != -1:
                result.append(True)
            else:
                result.append(False)
        if status == result:
            return True
    return False


async def _fetch_recruit_list(server: str, token: str, keyword: str = "") -> tuple[list[dict], str | None]:
    params = {"token": token, "server": server}
    if keyword:
        params["keyword"] = keyword
    url = f"{Config.jx3.api.url}/data/recruit/search"
    response = (await Request(url, params=params).get()).json()
    if response["code"] != 200:
        return [], None
    return response["data"]["data"], Time(response["data"]["time"]).format("%H:%M:%S")


async def _fetch_recruits(server: str, token: str, expr: Expr | None) -> tuple[list[dict], str | None]:
    api_keywords = pick_api_keywords(expr)
    if not api_keywords:
        return await _fetch_recruit_list(server, token)

    merged: list[dict] = []
    seen: set[tuple] = set()
    time_now: str | None = None
    for keyword in api_keywords:
        items, fetched_time = await _fetch_recruit_list(server, token, keyword)
        if fetched_time and time_now is None:
            time_now = fetched_time
        for detail in items:
            identity = recruit_identity(detail)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(detail)
    return merged, time_now


@token_required
async def get_recruit_image(
    server: str,
    query: str = "",
    local: bool = False,
    filter: bool = False,
    token: str = "",
):
    try:
        expr = parse_recruit_query(query)
    except ValueError as exc:
        return f"唔……查询语法有误：{exc}"

    data, time_now = await _fetch_recruits(server, token, expr)
    label = format_expr_label(expr)
    if not data:
        if expr is not None:
            return f"唔……未找到符合「{label}」的招募，请换个关键词试试！"
        return "唔……未找到相关团队，请检查后重试！"

    ad_flags = (await Request("https://inkar-suki.codethink.cn/filters").get()).json()
    time_now = time_now or Time().format("%H:%M:%S")
    contents = []
    for detail in data:
        if not matches_expr(detail, expr):
            continue
        content = detail["content"]
        if filter:
            if await check_ad(content, ad_flags):
                continue
        if local and detail["roomID"]:
            continue
        flag = (
            ""
            if not detail["roomID"]
            else '<img src="https://img.jx3box.com/image/box/servers.svg" style="width:20px;height:20px;">'
        )
        template = template_local if local else template_interserver
        if local:
            flag = ""
        contents.append(
            Template(template).render(
                sort=str(len(contents) + 1),
                name=detail["activity"],
                level=str(detail["level"]),
                leader=detail["leader"],
                count=f"{detail['number']}/{detail['maxNumber']}",
                content=content,
                time=Time(detail["createTime"]).format(),
                flag=flag,
            )
        )
        if len(contents) == 50:
            break
    if not contents:
        return f"唔……未找到符合「{label}」的招募，请换个关键词试试！"
    html = str(
        HTMLSourceCode(
            application_name=f"团队招募 · {label} · {time_now}",
            table_head=table_recruit_head,
            table_body="\n".join(contents),
        )
    )
    image = await generate(html, ".container", segment=True)
    return image

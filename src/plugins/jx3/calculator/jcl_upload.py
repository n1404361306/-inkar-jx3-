"""群 JCL 文件上传处理（群文件通知 + 群消息文件双通道）."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, GroupUploadNoticeEvent, Message
from nonebot.log import logger

from src.plugins.notice import notice
from src.plugins.preferences.app import Preference

from .jcl_analyze import (
    ASNAnalyze,
    BOSSAnalyze,
    CALAnalyze,
    CQCAnalyze,
    FALAnalyze,
    LGZAnalyze,
    LNXAnalyze,
    RODAnalyze,
    THFAnalyze,
    THRAnalyze,
    YXCAnalyze,
)
from .rdps import BLACalculator, TRDCalculator

_RECENT: dict[tuple[int, str], float] = {}
_DEDUP_SEC = 90

# 收到文件后先回复，再开始分析
_ANALYZER_ACK: dict[Callable, str] = {
    BLACalculator: "RHPS+RDPS 分析",
    TRDCalculator: "唐怀仁 P1 RDPS 分析",
    CQCAnalyze: "池清川分析",
    FALAnalyze: "前三次攻击记录分析",
    YXCAnalyze: "尹雪尘承伤统计",
    RODAnalyze: "重伤记录统计",
    CALAnalyze: "计算器 JCL 分析",
    ASNAnalyze: "阿史那承庆 汲取 QTE（破）排名 + 死侍索命期间治疗排名",
    BOSSAnalyze: "Boss 全程 DPS/HPS 榜单",
    THRAnalyze: "唐怀仁 P1 DPS/HPS 分析",
    THFAnalyze: "唐怀仁 P3 DPS 统计",
    LGZAnalyze: "柳公子传功与团灭分析",
    LNXAnalyze: "鲁念雪 减伤/治疗/化解贡献统计",
}


_JCL_BODY_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[\u4e00-\u9fff·\d]+(?:\(\d+\))?-[\u4e00-\u9fff·\d]+(?:\(\d+\))?\.jcl$"
)

_JCL_PREFIX_ANALYZERS: tuple[tuple[str, Callable], ...] = (
    ("BOSS-", BOSSAnalyze),
    ("BLA-", BLACalculator),
    ("TRD-", TRDCalculator),
    ("CQC-", CQCAnalyze),
    ("FAL-", FALAnalyze),
    ("YXC-", YXCAnalyze),
    ("ROD-", RODAnalyze),
    ("ASN-", ASNAnalyze),
    ("THR-", THRAnalyze),
    ("THF-", THFAnalyze),
    ("LGZ-", LGZAnalyze),
    ("LNX-", LNXAnalyze),
)


def check_jcl_name(filename: str, prefix: str) -> bool:
    if not filename.startswith(prefix):
        return False
    return bool(_JCL_BODY_PATTERN.match(filename[len(prefix) :]))


def resolve_analyzer(file_name: str) -> tuple[Callable, str] | None:
    if file_name.startswith("CAL-"):
        return CALAnalyze, "CAL-"
    for prefix, analyzer in _JCL_PREFIX_ANALYZERS:
        if check_jcl_name(file_name, prefix):
            return analyzer, prefix
    return None


def _dedup_check(group_id: int, file_name: str) -> bool:
    key = (group_id, file_name)
    now = time.time()
    if now - _RECENT.get(key, 0) < _DEDUP_SEC:
        return False
    return True


def _dedup_mark(group_id: int, file_name: str) -> None:
    key = (group_id, file_name)
    now = time.time()
    _RECENT[key] = now
    if len(_RECENT) > 200:
        cutoff = now - _DEDUP_SEC
        for k, ts in list(_RECENT.items()):
            if ts < cutoff:
                del _RECENT[k]


async def _resolve_file_url(bot: Bot, group_id: int, file_info: dict[str, Any]) -> str:
    if file_info.get("url"):
        return str(file_info["url"])
    file_id = file_info.get("id") or file_info.get("file_id")
    bus_id = file_info.get("busid") or file_info.get("bus_id")
    if not file_id or not bus_id:
        raise ValueError("缺少文件 id/busid，且无直链 url")
    file_data = await bot.call_api(
        "get_group_file_url",
        group_id=group_id,
        file_id=file_id,
        bus_id=bus_id,
    )
    return str(file_data["url"])


async def _send_jcl_ack(bot: Bot, group_id: int, file_name: str, analyzer: Callable) -> None:
    desc = _ANALYZER_ACK.get(analyzer, "JCL 分析")
    await bot.send_group_msg(
        group_id=group_id,
        message=f"收到 {file_name}，准备进行{desc}……",
    )


async def process_jcl_file(
    bot: Bot,
    group_id: int,
    user_id: int,
    file_name: str,
    file_info: dict[str, Any],
    *,
    source: str,
) -> None:
    resolved = resolve_analyzer(file_name)
    if resolved is None:
        return
    analyzer, prefix = resolved
    # 群文件通知无直链，且常与带 url 的群消息重复；让消息通道处理
    if source == "group_upload" and not file_info.get("url"):
        logger.info(f"JCL 群文件通知跳过，等待消息通道: {file_name}")
        return
    if not _dedup_check(group_id, file_name):
        logger.info(f"JCL 重复事件已跳过: {file_name} ({source})")
        return

    logger.info(f"JCL 分析开始: {file_name} 群{group_id} 来源={source}")
    is_anonymous = Preference(user_id, "", "").setting("匿名分析") == "开启"

    await _send_jcl_ack(bot, group_id, file_name, analyzer)

    try:
        if file_info.get("url"):
            url = str(file_info["url"])
        else:
            url = await _resolve_file_url(bot, group_id, file_info)
    except Exception as e:
        logger.exception(f"获取群文件 URL 失败: {file_name}")
        await bot.send_group_msg(group_id=group_id, message=f"JCL 分析失败：无法获取文件下载地址（{e}）")
        return

    try:
        result = await analyzer(file_name[len(prefix) :], url, is_anonymous, user_id)
        await bot.send_group_msg(group_id=group_id, message=Message(result))
        _dedup_mark(group_id, file_name)
        logger.info(f"JCL 分析完成: {file_name}")
    except json.decoder.JSONDecodeError:
        await bot.send_group_msg(
            group_id=group_id,
            message="啊哦，音卡的服务器目前似乎暂时有些小问题，请稍后再使用JCL分析？",
        )
    except MemoryError as e:
        await bot.send_group_msg(group_id=group_id, message=f"JCL 分析失败：{e}")
    except Exception as e:
        logger.exception(f"JCL 分析异常: {file_name}")
        await bot.send_group_msg(group_id=group_id, message=f"JCL 分析失败：{e}")


@notice.handle()
async def on_group_upload(bot: Bot, event: GroupUploadNoticeEvent) -> None:
    await process_jcl_file(
        bot,
        event.group_id,
        event.user_id,
        event.file.name,
        event.model_dump()["file"],
        source="group_upload",
    )


jcl_file_message = on_message(priority=4, block=False)


@jcl_file_message.handle()
async def on_group_file_message(bot: Bot, event: GroupMessageEvent) -> None:
    for seg in event.message:
        if seg.type != "file":
            continue
        data = seg.data
        file_name = str(data.get("file") or data.get("name") or "")
        if not file_name.lower().endswith(".jcl"):
            continue
        file_info = {
            "id": data.get("file_id") or data.get("id"),
            "busid": data.get("busid") or data.get("bus_id"),
            "url": data.get("url"),
        }
        if not file_info["url"] and not file_info["id"]:
            continue
        await process_jcl_file(
            bot,
            event.group_id,
            event.user_id,
            file_name,
            file_info,
            source="group_message",
        )
        return

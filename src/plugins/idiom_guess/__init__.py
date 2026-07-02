import asyncio
from asyncio import TimerHandle
from typing import Any, Dict

from nonebot import on_command, on_regex, require
from nonebot.adapters.onebot.v11 import Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg, RegexDict
from nonebot.plugin import PluginMetadata
from nonebot.utils import run_sync
from typing_extensions import Annotated

require("nonebot_plugin_alconna")
require("nonebot_plugin_session")

from nonebot_plugin_alconna import Image, Text, UniMessage
from nonebot_plugin_handle.data_source import GuessResult
from nonebot_plugin_session import SessionId, SessionIdType

from .data import random_idiom
from .game import IdiomHandle

__plugin_meta__ = PluginMetadata(
    name="猜成语",
    description="汉字 Wordle 猜成语（无需 @ 机器人）",
    usage=(
        "发送「猜成语」开始游戏；\n"
        "你有十次机会猜一个四字成语；\n"
        "每次猜测须为成语库中的成语，否则会提示不是成语；\n"
        "青色表示汉字在正确位置，橙色表示存在但位置不对；\n"
        "发送「提示」查看提示，发送「结束」结束游戏。"
    ),
    type="application",
    homepage="https://github.com/pwxcoo/chinese-xinhua",
)

games: Dict[str, IdiomHandle] = {}
timers: Dict[str, TimerHandle] = {}

UserId = Annotated[str, SessionId(SessionIdType.GROUP)]


def game_is_running(user_id: UserId) -> bool:
    return user_id in games


def game_not_running(user_id: UserId) -> bool:
    return user_id not in games


start = on_command(
    "猜成语",
    rule=game_not_running,
    priority=12,
    block=True,
)
hint = on_command("提示", rule=game_is_running, priority=13, block=True)
stop = on_command(
    "结束",
    aliases={"结束游戏", "结束猜成语"},
    rule=game_is_running,
    priority=13,
    block=True,
)
guess = on_regex(
    r"^(?P<idiom>[\u4e00-\u9fa5]{4})$",
    rule=game_is_running,
    block=True,
    priority=14,
)


def stop_game(user_id: str):
    if timer := timers.pop(user_id, None):
        timer.cancel()
    games.pop(user_id, None)


async def stop_game_timeout(matcher: Matcher, user_id: str):
    game = games.get(user_id)
    stop_game(user_id)
    if game:
        msg = "猜成语超时，游戏结束。"
        if len(game.guessed_idiom) >= 1:
            msg += f"\n{game.result}"
        await matcher.finish(msg)


def set_timeout(matcher: Matcher, user_id: str, timeout: float = 300):
    if timer := timers.get(user_id):
        timer.cancel()
    loop = asyncio.get_running_loop()
    timers[user_id] = loop.call_later(
        timeout, lambda: asyncio.ensure_future(stop_game_timeout(matcher, user_id))
    )


@start.handle()
async def _(matcher: Matcher, user_id: UserId, args: Message = CommandArg()):
    if args.extract_plain_text().strip():
        return
    idiom, explanation = random_idiom()
    game = IdiomHandle(idiom, explanation)
    games[user_id] = game
    set_timeout(matcher, user_id)
    msg = Text(
        f"你有{game.times}次机会猜一个四字成语，请发送成语库中的成语参与游戏。"
    ) + Image(raw=await run_sync(game.draw)())
    await msg.send()


@hint.handle()
async def _(matcher: Matcher, user_id: UserId):
    game = games[user_id]
    set_timeout(matcher, user_id)
    await UniMessage.image(raw=await run_sync(game.draw_hint)()).send()


@stop.handle()
async def _(matcher: Matcher, user_id: UserId):
    game = games[user_id]
    stop_game(user_id)
    msg = "游戏已结束"
    if len(game.guessed_idiom) >= 1:
        msg += f"\n{game.result}"
    await matcher.finish(msg)


@guess.handle()
async def _(matcher: Matcher, user_id: UserId, matched: Dict[str, Any] = RegexDict()):
    game = games[user_id]
    set_timeout(matcher, user_id)
    idiom = str(matched["idiom"])
    result = game.guess(idiom)

    if result in (GuessResult.WIN, GuessResult.LOSS):
        stop_game(user_id)
        msg = Text(
            (
                "恭喜你猜出了成语！"
                if result == GuessResult.WIN
                else "很遗憾，没有人猜出来呢"
            )
            + f"\n{game.result}"
        ) + Image(raw=await run_sync(game.draw)())
        await msg.send()
    elif result == GuessResult.DUPLICATE:
        await matcher.finish("你已经猜过这个成语了呢")
    elif result == GuessResult.ILLEGAL:
        await matcher.finish(f"「{idiom}」不是成语，请发送有效的四字成语。")
    else:
        await UniMessage.image(raw=await run_sync(game.draw)()).send()

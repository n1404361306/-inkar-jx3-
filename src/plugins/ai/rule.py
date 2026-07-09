import re

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.rule import Rule

from src.config import Config


async def _bot_names_in_group(bot: Bot, event: GroupMessageEvent) -> set[str]:
    names = {Config.bot_basic.bot_name, "音卡", "Inkar Suki", "Inkar"}
    try:
        info = await bot.call_api(
            "get_group_member_info",
            group_id=event.group_id,
            user_id=event.self_id,
            no_cache=True,
        )
        for key in ("nickname", "card"):
            value = info.get(key)
            if value:
                names.add(str(value))
    except Exception:
        pass
    return {name for name in names if name}


def _plain_at_name(text: str) -> str | None:
    match = re.match(r"^@([^\s@]+)", text.strip())
    return match.group(1) if match else None


async def _is_at_bot(bot: Bot, event: MessageEvent) -> bool:
    if event.is_tome():
        return True

    plain = event.get_plaintext().strip()
    at_name = _plain_at_name(plain)
    if not at_name:
        return False

    if isinstance(event, GroupMessageEvent):
        return at_name in await _bot_names_in_group(bot, event)

    return at_name in {Config.bot_basic.bot_name, "音卡"}


def extract_question(event: MessageEvent) -> str:
    text = event.get_message().extract_plain_text().strip()
    if text:
        return text

    plain = event.get_plaintext().strip()
    return re.sub(r"^@[^\s@]+\s*", "", plain).strip()


at_bot = Rule(_is_at_bot)

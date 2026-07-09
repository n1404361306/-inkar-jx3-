from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.log import logger

from src.config import Config
from src.utils.ai.deepseek import DeepSeekError, chat

from .quota import refund, try_consume
from .rule import at_bot, extract_question

ai_chat_matcher = on_message(rule=at_bot, priority=6, block=False)


async def _is_admin(bot: Bot, event: MessageEvent) -> bool:
    if str(event.user_id) in Config.bot_basic.bot_owner:
        return True
    if isinstance(event, GroupMessageEvent):
        try:
            info = await bot.call_api(
                "get_group_member_info",
                group_id=event.group_id,
                user_id=event.user_id,
                no_cache=True,
            )
            return info.get("role") in ("owner", "admin")
        except Exception:
            return False
    return False


@ai_chat_matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    if not Config.deepseek.enable:
        return

    question = extract_question(event)
    if not question:
        await ai_chat_matcher.finish("在呢！有什么事直接说就好~")

    admin = await _is_admin(bot, event)
    allowed, used, limit = try_consume(event.user_id, unlimited=admin)
    if not allowed:
        await ai_chat_matcher.finish(
            f"唔……今天的 AI 互动次数已经用完啦（{used}/{limit} 次）。\n明天再来找音卡吧~"
        )

    try:
        reply = await chat(question)
    except DeepSeekError as exc:
        if not admin:
            refund(event.user_id)
        await ai_chat_matcher.finish(f"唔……音卡暂时想不出答案：{exc}")
    except Exception as exc:
        logger.exception("AI 对话处理失败")
        if not admin:
            refund(event.user_id)
        await ai_chat_matcher.finish("唔……音卡刚才走神了，稍后再试试吧~")

    if not reply:
        if not admin:
            refund(event.user_id)
        await ai_chat_matcher.finish("唔……音卡一时不知道该怎么回答，换个问法试试吧~")

    suffix = ""
    if not admin:
        remaining = limit - used
        suffix = f"\n\n（今日剩余 {remaining}/{limit} 次）"

    await ai_chat_matcher.finish(reply + suffix)

from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message, GroupMessageEvent

from src.config import Config
from src.const.prompts import PROMPT
from src.utils.database.operation import get_group_settings

from .api import get_recruit_image
from .parse import parse_recruit_args

recruit_matcher = on_command("jx3_recruit", aliases={"招募"}, force_whitespace=True, priority=5)


@recruit_matcher.handle()
async def _(event: GroupMessageEvent, full_argument: Message = CommandArg()):
    if not Config.jx3.api.enable:
        return
    additions = get_group_settings(str(event.group_id), "additions")
    if not isinstance(additions, list):
        return
    filter_ads = "招募过滤" in additions

    args = [arg for arg in full_argument.extract_plain_text().split() if arg]
    server, query = parse_recruit_args(args, event.group_id)
    if server is None:
        await recruit_matcher.finish(PROMPT.ServerNotExist)

    data = await get_recruit_image(server, query, False, filter_ads)
    await recruit_matcher.finish(data)

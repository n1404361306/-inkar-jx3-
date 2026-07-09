from datetime import datetime
from typing import Any

from src.config import Config
from src.utils.database import cache_db
from src.utils.database.classes import AIChatUsage


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_usage_count(user_id: int) -> int:
    record: AIChatUsage | Any = cache_db.where_one(
        AIChatUsage(),
        "user_id = ? AND usage_date = ?",
        int(user_id),
        _today(),
        default=None,
    )
    return record.count if record is not None else 0


def try_consume(user_id: int, *, unlimited: bool = False) -> tuple[bool, int, int]:
    """
    尝试消耗一次 AI 互动配额。

    Returns:
        (allowed, used_count, daily_limit)
    """
    limit = Config.deepseek.daily_limit
    if unlimited:
        return True, get_usage_count(user_id), limit

    today = _today()
    record: AIChatUsage | Any = cache_db.where_one(
        AIChatUsage(),
        "user_id = ? AND usage_date = ?",
        int(user_id),
        today,
        default=AIChatUsage(user_id=int(user_id), usage_date=today, count=0),
    )

    if record.count >= limit:
        return False, record.count, limit

    record.count += 1
    cache_db.save(record)
    return True, record.count, limit


def refund(user_id: int) -> None:
    """API 调用失败时回退一次配额。"""
    today = _today()
    record: AIChatUsage | Any = cache_db.where_one(
        AIChatUsage(),
        "user_id = ? AND usage_date = ?",
        int(user_id),
        today,
        default=None,
    )
    if record is not None and record.count > 0:
        record.count -= 1
        cache_db.save(record)

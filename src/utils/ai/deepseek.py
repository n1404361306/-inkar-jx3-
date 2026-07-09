from typing import Any
import re

import httpx

from src.config import Config
from src.utils.ai.prompt import SYSTEM_PROMPT


class DeepSeekError(Exception):
    pass


async def chat(user_message: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    cfg = Config.deepseek
    if not cfg.api_key:
        raise DeepSeekError("未配置 DeepSeek API Key")

    url = f"{cfg.base_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise DeepSeekError("请求超时，请稍后再试") from exc
        except httpx.HTTPError as exc:
            raise DeepSeekError("网络异常，请稍后再试") from exc

    if response.status_code != 200:
        detail = response.text[:200]
        raise DeepSeekError(f"API 请求失败 ({response.status_code}): {detail}")

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("API 返回格式异常") from exc

    text = strip_markdown(str(content or "").strip())
    if not text:
        raise DeepSeekError("没有生成有效回复")
    return truncate_reply(text, cfg.max_reply_length)


def strip_markdown(text: str) -> str:
    """移除常见 Markdown 格式，保留纯文字。"""
    text = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip("`").strip(), text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    return text.strip()


def truncate_reply(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"

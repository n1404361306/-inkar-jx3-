from typing import Optional

from nonebot_plugin_handle.data_source import GuessResult, Handle

from .data import is_valid_idiom


class IdiomHandle(Handle):
    def __init__(self, idiom: str, explanation: str):
        super().__init__(idiom, explanation, strict=False)

    def guess(self, idiom: str) -> Optional[GuessResult]:
        if not is_valid_idiom(idiom):
            return GuessResult.ILLEGAL
        return super().guess(idiom)

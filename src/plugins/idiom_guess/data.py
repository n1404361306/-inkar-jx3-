"""成语词库，数据来源于 https://github.com/pwxcoo/chinese-xinhua"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

IDIOM_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "source" / "idiom_guess" / "idiom.json"
)


@lru_cache(maxsize=1)
def _load_data() -> tuple[set[str], List[Dict[str, str]]]:
    with IDIOM_PATH.open(encoding="utf-8") as f:
        entries: List[Dict[str, str]] = json.load(f)
    all_words = {entry["word"] for entry in entries}
    answers = [
        {"word": entry["word"], "explanation": entry.get("explanation", "")}
        for entry in entries
        if len(entry["word"]) == 4
    ]
    return all_words, answers


def is_valid_idiom(word: str) -> bool:
    return word in _load_data()[0]


def random_idiom() -> Tuple[str, str]:
    answer = random.choice(_load_data()[1])
    return answer["word"], answer["explanation"]

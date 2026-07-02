"""通用 Boss JCL 流式解析：元数据 + 战斗区间."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..lgz.lua_table import LuaTableAnalyserToDict
from ..lgz.parser import check_memory_available, fix_gbk

MAX_BOSS_JCL_BYTES = 48 * 1024 * 1024

NEED_TYPES_PASS1 = frozenset({b"1", b"4", b"5", b"8", b"9"})
NEED_TYPES_STATS = frozenset({b"13", b"21"})

_FILE_META_RE = re.compile(
    r"^\d{4}(?:-\d{2}){5}-(?P<dungeon>.+?)\(\d+\)-(?P<boss>.+?)\((?P<boss_id>\d+)\)\.jcl$"
)


@dataclass
class BossPlayerInfo:
    pid: str
    name: str
    school: str
    xf_id: int


@dataclass
class BossBattleWindow:
    start_ms: int
    end_ms: int
    source: str = ""


@dataclass
class BossJCLMeta:
    server: str = ""
    dungeon: str = ""
    boss_name: str = ""
    boss_template_id: str = ""
    players: dict[str, BossPlayerInfo] = field(default_factory=dict)
    npc_ids: set[str] = field(default_factory=set)
    battle: BossBattleWindow | None = None
    sum_time_ms: int = 0


def parse_file_name_meta(file_name: str) -> tuple[str, str, str]:
    match = _FILE_META_RE.match(file_name)
    if not match:
        raise ValueError(
            "文件名格式不正确，应为：BOSS-YYYY-MM-DD-HH-MM-SS-副本名(id)-首领名(id).jcl"
        )
    return match.group("dungeon"), match.group("boss"), match.group("boss_id")


def _decode_payload(raw: bytes) -> str:
    for enc in ("gbk", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_lua(lta: LuaTableAnalyserToDict, blob: bytes) -> dict[str, Any] | None:
    try:
        return lta.analyse(_decode_payload(blob), delta=1)
    except Exception:
        return None


def _is_true(v: Any) -> bool:
    return str(v).lower() in ("true", "1")


def _iter_lines(path: str):
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                yield line


def _check_file_size(path: str) -> None:
    size = os.path.getsize(path)
    if size > MAX_BOSS_JCL_BYTES:
        raise ValueError(
            f"JCL 文件过大（{size / 1024 / 1024:.1f}MB），"
            f"上限 {MAX_BOSS_JCL_BYTES // 1024 // 1024}MB"
        )
    check_memory_available()


def scan_boss_meta(path: str, file_name: str) -> BossJCLMeta:
    """第一遍：玩家/NPC/首领战斗区间."""
    _check_file_size(path)
    dungeon, boss_name, boss_template_id = parse_file_name_meta(file_name)
    meta = BossJCLMeta(
        dungeon=dungeon,
        boss_name=boss_name,
        boss_template_id=boss_template_id,
    )
    lta = LuaTableAnalyserToDict()

    npc_template: dict[str, str] = {}
    npc_name: dict[str, str] = {}
    boss_npc_ids: set[str] = set()
    battle_start: int | None = None
    battle_end: int | None = None
    first_combat_ts: int | None = None
    last_combat_ts: int | None = None

    for line in _iter_lines(path):
        parts = line.split(b"\t", 5)
        if len(parts) < 6:
            continue
        et = parts[4]
        try:
            ts = int(parts[3])
        except ValueError:
            continue

        if et in NEED_TYPES_STATS:
            first_combat_ts = ts if first_combat_ts is None else min(first_combat_ts, ts)
            last_combat_ts = ts if last_combat_ts is None else max(last_combat_ts, ts)

        if et not in NEED_TYPES_PASS1:
            continue

        payload = _parse_lua(lta, parts[5])
        if payload is None:
            continue

        if et == b"1":
            if not meta.server:
                try:
                    meta.server = payload["2"].split(":")[2].split("_")[1]
                except Exception:
                    pass
            try:
                meta.sum_time_ms = max(meta.sum_time_ms, int(payload.get("3") or 0))
            except (TypeError, ValueError):
                pass
        elif et == b"4":
            pid = str(payload["1"])
            xf = int(payload.get("4") or 0)
            meta.players[pid] = BossPlayerInfo(
                pid=pid,
                name=fix_gbk(payload.get("2", "")),
                school=str(payload.get("3", "")),
                xf_id=xf,
            )
        elif et == b"8":
            nid = str(payload["1"])
            meta.npc_ids.add(nid)
            template_id = str(payload.get("3", ""))
            name = fix_gbk(str(payload.get("2", "")))
            npc_template[nid] = template_id
            npc_name[nid] = name
            if template_id == boss_template_id:
                boss_npc_ids.add(nid)
            elif boss_name and boss_name in name:
                boss_npc_ids.add(nid)
        elif et in (b"5", b"9"):
            nid = str(payload.get("1", ""))
            if nid not in boss_npc_ids:
                continue
            if _is_true(payload.get("2")):
                battle_start = ts if battle_start is None else min(battle_start, ts)
            elif battle_start is not None and ts > battle_start:
                battle_end = max(battle_end or ts, ts)

    window_source = ""
    if battle_start is not None and battle_end is not None and battle_end > battle_start:
        window_source = "首领进战/脱战"
        meta.battle = BossBattleWindow(
            start_ms=battle_start,
            end_ms=battle_end,
            source=window_source,
        )
    elif battle_start is not None and meta.sum_time_ms > 0:
        window_source = "首领进战 + 记录时长"
        meta.battle = BossBattleWindow(
            start_ms=battle_start,
            end_ms=battle_start + meta.sum_time_ms,
            source=window_source,
        )
    elif first_combat_ts is not None and last_combat_ts is not None and last_combat_ts > first_combat_ts:
        window_source = "战斗事件时间范围"
        meta.battle = BossBattleWindow(
            start_ms=first_combat_ts,
            end_ms=last_combat_ts,
            source=window_source,
        )
    else:
        raise ValueError(
            f"未识别到首领「{boss_name}」的战斗区间，请确认 JCL 完整且文件名首领 ID 正确"
        )

    if len(meta.players) < 2:
        raise ValueError("JCL 中玩家数量不足，请确认文件完整")
    return meta


def iter_boss_combat_events(path: str, window: BossBattleWindow):
    """流式 yield 战斗窗口内的 type13/21."""
    lta = LuaTableAnalyserToDict()
    start, end = window.start_ms, window.end_ms
    for line in _iter_lines(path):
        parts = line.split(b"\t", 5)
        if len(parts) < 6 or parts[4] not in NEED_TYPES_STATS:
            continue
        try:
            ts = int(parts[3])
        except ValueError:
            continue
        if ts < start or ts > end:
            continue
        payload = _parse_lua(lta, parts[5])
        if payload is None:
            continue
        yield ts, parts[4].decode("ascii"), payload


def battle_time_sec(window: BossBattleWindow) -> float:
    return max(1.0, (window.end_ms - window.start_ms) / 1000.0)

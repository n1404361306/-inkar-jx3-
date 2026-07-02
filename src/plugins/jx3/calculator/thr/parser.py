"""唐怀仁 JCL 流式解析：元数据 + P1 边界（不缓存全量事件）."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ..lgz.lua_table import LuaTableAnalyserToDict
from ..lgz.parser import check_memory_available, fix_gbk

MAX_THR_JCL_BYTES = 48 * 1024 * 1024

THR_BOSS_ID = "1075547542"
XLJK_BOSS_ID = "1075547539"
P1_SHOUT_MIN_MS = 5000

NEED_TYPES_PASS1 = frozenset({b"1", b"4", b"5", b"8", b"9", b"14"})
NEED_TYPES_STATS = frozenset({b"13", b"21"})


@dataclass
class ThrPlayerInfo:
    pid: str
    name: str
    school: str
    xf_id: int


@dataclass
class ThrP1Window:
    start_ms: int
    end_ms: int
    end_shout: str = ""


@dataclass
class ThrJCLMeta:
    server: str = ""
    players: dict[str, ThrPlayerInfo] = field(default_factory=dict)
    npc_ids: set[str] = field(default_factory=set)
    p1: ThrP1Window | None = None


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
    if size > MAX_THR_JCL_BYTES:
        raise ValueError(
            f"JCL 文件过大（{size / 1024 / 1024:.1f}MB），"
            f"上限 {MAX_THR_JCL_BYTES // 1024 // 1024}MB"
        )
    check_memory_available()


def scan_thr_meta(path: str) -> ThrJCLMeta:
    """第一遍：玩家/NPC/P1 边界（仅解析必要 type）."""
    _check_file_size(path)
    meta = ThrJCLMeta()
    lta = LuaTableAnalyserToDict()
    p1_start: int | None = None
    p1_end: int | None = None
    p1_shout = ""

    for line in _iter_lines(path):
        parts = line.split(b"\t", 5)
        if len(parts) < 6:
            continue
        et = parts[4]
        if et not in NEED_TYPES_PASS1:
            continue
        try:
            ts = int(parts[3])
        except ValueError:
            continue
        payload = _parse_lua(lta, parts[5])
        if payload is None:
            continue

        if et == b"1" and not meta.server:
            try:
                meta.server = payload["2"].split(":")[2].split("_")[1]
            except Exception:
                pass
        elif et == b"4":
            pid = str(payload["1"])
            xf = int(payload.get("4") or 0)
            meta.players[pid] = ThrPlayerInfo(
                pid=pid,
                name=fix_gbk(payload.get("2", "")),
                school=str(payload.get("3", "")),
                xf_id=xf,
            )
        elif et == b"8":
            meta.npc_ids.add(str(payload["1"]))
        elif et in (b"5", b"9"):
            nid = str(payload.get("1", ""))
            if nid == THR_BOSS_ID and _is_true(payload.get("2")):
                p1_start = ts if p1_start is None else min(p1_start, ts)
        elif et == b"14":
            speaker = str(payload.get("2", ""))
            content = fix_gbk(str(payload.get("1", "")))
            if (
                p1_end is None
                and speaker == XLJK_BOSS_ID
                and p1_start is not None
                and ts > p1_start + P1_SHOUT_MIN_MS
            ):
                p1_end = ts
                p1_shout = content

    if p1_start is None or p1_end is None:
        raise ValueError("未识别到唐怀仁 P1 战斗区间（需唐怀仁进战 + 须罗巨傀转阶段喊话）")

    meta.p1 = ThrP1Window(start_ms=p1_start, end_ms=p1_end, end_shout=p1_shout)
    if len(meta.players) < 2:
        raise ValueError("JCL 中玩家数量不足，请确认文件完整")
    return meta


def iter_p1_combat_events(path: str, window: ThrP1Window):
    """第二/三遍：仅 yield P1 窗口内的 type13/21 原始行（流式）."""
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


def battle_time_sec(window: ThrP1Window) -> float:
    return max(1.0, (window.end_ms - window.start_ms) / 1000.0)

"""阿史那承庆 JCL 流式解析."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterator

from ..lgz.lua_table import LuaTableAnalyserToDict
from ..lgz.parser import check_memory_available, fix_gbk

MAX_ASN_JCL_BYTES = 64 * 1024 * 1024
ASN_BOSS_TEMPLATE = 137130

NEED_META = frozenset({b"1", b"4", b"8"})
NEED_STATS = frozenset({b"13", b"21", b"19"})


@dataclass
class AsnPlayerInfo:
    pid: str
    name: str
    school: str
    xf_id: int


@dataclass
class AsnJCLMeta:
    server: str = ""
    boss_id: str = ""
    players: dict[str, AsnPlayerInfo] = field(default_factory=dict)
    summon: dict[str, str] = field(default_factory=dict)
    base_ms: int = 0
    end_ms: int = 0
    sum_time_ms: int = 0


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


def _check_file_size(path: str) -> None:
    size = os.path.getsize(path)
    if size > MAX_ASN_JCL_BYTES:
        raise ValueError(
            f"JCL 文件过大（{size / 1024 / 1024:.1f}MB），"
            f"上限 {MAX_ASN_JCL_BYTES // 1024 // 1024}MB"
        )
    check_memory_available()


def _iter_lines(path: str) -> Iterator[bytes]:
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                yield line


def scan_asn_meta(path: str) -> AsnJCLMeta:
    _check_file_size(path)
    meta = AsnJCLMeta()
    lta = LuaTableAnalyserToDict()
    name_to_pid: dict[str, str] = {}
    first_info = True

    for line in _iter_lines(path):
        parts = line.split(b"\t", 5)
        if len(parts) < 6:
            continue
        et = parts[4]
        if et not in NEED_META and et != b"1":
            continue
        try:
            ts = int(parts[3])
        except ValueError:
            continue
        payload = _parse_lua(lta, parts[5])
        if payload is None:
            continue

        if meta.base_ms == 0:
            meta.base_ms = ts
        meta.base_ms = min(meta.base_ms, ts)
        meta.end_ms = max(meta.end_ms, ts)

        if et == b"1":
            if first_info:
                try:
                    meta.server = payload["2"].split(":")[2].split("_")[1]
                except Exception:
                    pass
                first_info = False
            else:
                meta.sum_time_ms = int(payload.get("3") or 0)
        elif et == b"4":
            pid = str(payload["1"])
            xf = int(payload.get("4") or 0)
            name = fix_gbk(str(payload.get("2", "")))
            meta.players[pid] = AsnPlayerInfo(
                pid=pid,
                name=name,
                school=str(payload.get("3", "")),
                xf_id=xf,
            )
            name_to_pid[name] = pid
        elif et == b"8":
            tpl = int(payload.get("3") or 0)
            if tpl == ASN_BOSS_TEMPLATE and not meta.boss_id:
                meta.boss_id = str(payload["1"])
            nid = str(payload["1"])
            nm = fix_gbk(str(payload.get("2", "")))
            if "的" in nm:
                cand = "的".join(nm.split("的")[:-1])
                if cand in name_to_pid:
                    meta.summon[nid] = name_to_pid[cand]
            owner = str(payload.get("4") or "0")
            if owner != "0":
                meta.summon[nid] = owner

    if not meta.boss_id:
        raise ValueError("未识别到阿史那承庆（n137130），请确认 JCL 完整且为对应首领战")
    if len(meta.players) < 2:
        raise ValueError("JCL 中玩家数量不足，请确认文件完整")
    if meta.sum_time_ms <= 0 and meta.end_ms > meta.base_ms:
        meta.sum_time_ms = meta.end_ms - meta.base_ms
    return meta


def resolve_caster(meta: AsnJCLMeta, raw_id: str) -> str:
    return meta.summon.get(raw_id, raw_id)


def iter_combat_events(path: str) -> Iterator[tuple[int, str, dict[str, Any]]]:
    lta = LuaTableAnalyserToDict()
    for line in _iter_lines(path):
        parts = line.split(b"\t", 5)
        if len(parts) < 6 or parts[4] not in NEED_STATS:
            continue
        try:
            ts = int(parts[3])
        except ValueError:
            continue
        payload = _parse_lua(lta, parts[5])
        if payload is None:
            continue
        yield ts, parts[4].decode("ascii"), payload

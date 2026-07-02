"""阿史那承庆：汲取波次 QTE（破）+ 死侍轮次索命期间治疗."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..lgz.lua_table import LuaTableAnalyserToDict
from .parser import AsnJCLMeta, iter_combat_events, resolve_caster, scan_asn_meta

SKILL_JIQU = 44443
SKILL_QTE_PO = 44194
SKILL_QTE_SUI = 44610

BUFF_DEAD_SERVANT = 32951  # 死侍，用于划分轮次
BUFF_SUOMING = 33574  # 索命（死侍玩家身上可被治疗的状态标记）
BUFF_JIQU_DR = 33530  # 汲取减伤（QTE 击破目标）
# 同机制在 JCL 中可能记录为不同 buff id（随阶段变化）
JIQU_DR_BUFF_IDS = (BUFF_JIQU_DR, 33446, 33406)

JIQU_CLUSTER_GAP_MS = 30_000
JIQU_WINDOW_MS = 20_000
DEAD_SERVANT_CLUSTER_GAP_MS = 20_000
DEAD_SERVANT_TAIL_MS = 12_000
SUOMING_ROUND_TAIL_MS = 2_000


@dataclass
class RankEntry:
    pid: str
    name: str
    xf_id: int
    value: int
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class JiquWave:
    index: int
    start_ms: int
    end_ms: int
    start_rel: str
    qte_po: list[RankEntry] = field(default_factory=list)


@dataclass
class DeadServantRound:
    index: int
    start_ms: int
    end_ms: int
    start_rel: str
    servant_count: int
    shield_heal: list[RankEntry] = field(default_factory=list)


@dataclass
class AsnAnalysisResult:
    meta: AsnJCLMeta
    base_ms: int
    jiqu_waves: list[JiquWave] = field(default_factory=list)
    dead_rounds: list[DeadServantRound] = field(default_factory=list)


def ms_hms(ms: int, base: int) -> str:
    s = max(0, ms - base) // 1000
    m, sec = divmod(s, 60)
    return f"{m:02d}:{sec:02d}"


def suoming_shield_amount(result: dict[str, Any]) -> int:
    """索命期间奶盾有效量：盾吸收(8) + 溢出到盾的治疗(6-14)."""
    heal = int(result.get("6", 0) or 0)
    shield = int(result.get("8", 0) or 0)
    effective = int(result.get("14", 0) or 0)
    amount = shield
    if heal > 0:
        amount += max(heal - effective, 0)
    return amount


def _build_jiqu_windows(jiqu_hits: list[int]) -> list[tuple[int, int]]:
    if not jiqu_hits:
        return []
    wave_starts: list[int] = []
    for t in sorted(set(jiqu_hits)):
        if not wave_starts or t - wave_starts[-1] >= JIQU_CLUSTER_GAP_MS:
            wave_starts.append(t)
    return [(hit_t, hit_t + JIQU_WINDOW_MS) for hit_t in wave_starts]


def _scan_boss_jiqu_dr_timeline(path: str, boss_id: str) -> list[tuple[int, bool]]:
    """扫描 Boss 身上汲取减伤 buff 是否存在（et8/12/13）."""
    lta = LuaTableAnalyserToDict()
    stacks = {bid: 0 for bid in JIQU_DR_BUFF_IDS}
    timeline: list[tuple[int, bool]] = []

    def snapshot(ts: int) -> None:
        active = any(stacks[bid] > 0 for bid in JIQU_DR_BUFF_IDS)
        if timeline and timeline[-1][0] == ts:
            timeline[-1] = (ts, active)
        else:
            timeline.append((ts, active))

    with open(path, "rb") as f:
        for line in f:
            parts = line.split(b"\t", 5)
            if len(parts) < 6:
                continue
            et = parts[4].decode("ascii", errors="ignore")
            if et not in ("8", "12", "13"):
                continue
            try:
                ts = int(parts[3])
            except ValueError:
                continue
            payload = lta.analyse(parts[5].decode("gbk", errors="replace"), delta=1)
            if payload is None:
                continue

            if et == "8":
                if str(payload.get("1")) != boss_id:
                    continue
                bid = int(payload.get("6") or 0)
                if bid not in stacks:
                    continue
                stacks[bid] = int(payload.get("8") or 0)
                snapshot(ts)
            elif et == "12":
                vals = [payload[k] for k in sorted(payload, key=lambda x: int(x))]
                if len(vals) < 4:
                    continue
                bid = int(vals[3])
                if bid not in stacks:
                    continue
                stacks[bid] = 0
                snapshot(ts)
            elif et == "13":
                if str(payload.get("1")) != boss_id:
                    continue
                bid = int(payload.get("5") or 0)
                if bid not in stacks:
                    continue
                if payload.get("2") in (True, "true"):
                    stacks[bid] = 0
                    snapshot(ts)

    return timeline


def _jiqu_dr_active_at(timeline: list[tuple[int, bool]], ts: int) -> bool:
    active = False
    for change_ts, is_active in timeline:
        if change_ts <= ts:
            active = is_active
        else:
            break
    return active


def _count_qte_in_window(
    qte_events: list[tuple[int, str, int]],
    start: int,
    end: int,
    dr_timeline: list[tuple[int, bool]],
) -> tuple[dict[str, int], dict[str, int]]:
    """统计窗口内有效 QTE：Boss 汲取减伤仍在 + 同一玩家同一秒最多计 1 次."""
    po_secs: dict[str, set[int]] = {}
    sui_secs: dict[str, set[int]] = {}
    counts: dict[str, int] = {}
    bad_counts: dict[str, int] = {}
    for ts, pid, sid in qte_events:
        if not (start <= ts < end):
            continue
        if not _jiqu_dr_active_at(dr_timeline, ts):
            continue
        sec = ts // 1000
        if sid == SKILL_QTE_PO:
            if sec not in po_secs.setdefault(pid, set()):
                po_secs[pid].add(sec)
                counts[pid] = counts.get(pid, 0) + 1
        elif sid == SKILL_QTE_SUI:
            if sec not in sui_secs.setdefault(pid, set()):
                sui_secs[pid].add(sec)
                bad_counts[pid] = bad_counts.get(pid, 0) + 1
    return counts, bad_counts


def _cluster_dead_rounds(
    applies: list[tuple[int, str]],
    removes_32951: dict[str, list[int]],
    removes_33574: dict[str, list[int]],
    end_ms: int,
) -> list[tuple[int, int, int, set[str], int]]:
    if not applies:
        return []
    applies = sorted(applies)
    clusters: list[list[tuple[int, str]]] = [[applies[0]]]
    for item in applies[1:]:
        if item[0] - clusters[-1][0][0] < DEAD_SERVANT_CLUSTER_GAP_MS:
            clusters[-1].append(item)
        else:
            clusters.append([item])

    rounds: list[tuple[int, int, int, set[str], int]] = []
    for cluster in clusters:
        start = cluster[0][0]
        last_apply = cluster[-1][0]
        players = {pid for _, pid in cluster}
        remove_times: list[int] = []
        for pid in players:
            for t in removes_33574.get(pid, []):
                if t >= start:
                    remove_times.append(t)
                    break
            else:
                for t in removes_32951.get(pid, []):
                    if t >= start:
                        remove_times.append(t)
                        break
        end = max(remove_times) if remove_times else last_apply + DEAD_SERVANT_TAIL_MS
        end = min(max(end, last_apply) + SUOMING_ROUND_TAIL_MS, end_ms + 1)
        rounds.append((start, end, len(players), players, last_apply))
    return rounds


def compute_asn(path: str) -> AsnAnalysisResult:
    meta = scan_asn_meta(path)
    boss = meta.boss_id
    base = meta.base_ms

    jiqu_hits: list[int] = []
    qte_events: list[tuple[int, str, int]] = []
    ds_apply: list[tuple[int, str]] = []
    removes_32951: dict[str, list[int]] = {}
    removes_33574: dict[str, list[int]] = {}

    suoming_active: dict[str, int] = {}
    heal_events: list[tuple[int, str, str, int, int, int]] = []

    for ts, et, payload in iter_combat_events(path):
        if et == "21":
            caster = resolve_caster(meta, str(payload.get("1", "")))
            target = str(payload.get("2", ""))
            sid = int(payload.get("5") or 0)
            if caster == boss and sid == SKILL_JIQU:
                jiqu_hits.append(ts)
            if target == boss and sid in (SKILL_QTE_PO, SKILL_QTE_SUI) and caster in meta.players:
                qte_events.append((ts, caster, sid))
            apply_ts = suoming_active.get(target)
            if apply_ts is not None and apply_ts <= ts:
                amount = suoming_shield_amount(payload.get("9") or {})
                if amount > 0 and caster in meta.players:
                    heal_events.append((ts, caster, target, sid, amount, apply_ts))
        elif et == "13":
            bid = int(payload.get("5") or 0)
            tgt = str(payload.get("1", ""))
            deleted = payload.get("2") in (True, "true")
            if bid == BUFF_DEAD_SERVANT:
                if deleted:
                    removes_32951.setdefault(tgt, []).append(ts)
                else:
                    ds_apply.append((ts, tgt))
            elif bid == BUFF_SUOMING:
                if deleted:
                    suoming_active.pop(tgt, None)
                    removes_33574.setdefault(tgt, []).append(ts)
                else:
                    suoming_active[tgt] = ts

    dr_timeline = _scan_boss_jiqu_dr_timeline(path, boss)
    jiqu_windows = _build_jiqu_windows(jiqu_hits)
    dead_rounds = _cluster_dead_rounds(ds_apply, removes_32951, removes_33574, meta.end_ms)

    result = AsnAnalysisResult(meta=meta, base_ms=base)

    for i, (start, end) in enumerate(jiqu_windows, 1):
        counts, bad_counts = _count_qte_in_window(qte_events, start, end, dr_timeline)
        ranked = sorted(counts.items(), key=lambda x: (-x[1], meta.players[x[0]].name))
        wave = JiquWave(
            index=i,
            start_ms=start,
            end_ms=end,
            start_rel=ms_hms(start, base),
            qte_po=[
                RankEntry(
                    pid=pid,
                    name=meta.players[pid].name,
                    xf_id=meta.players[pid].xf_id,
                    value=cnt,
                    extra={"bad": bad_counts.get(pid, 0)},
                )
                for pid, cnt in ranked
            ],
        )
        result.jiqu_waves.append(wave)

    for i, (start, end, count, players, last_apply) in enumerate(dead_rounds, 1):
        totals: dict[str, int] = {}
        skill_hits: dict[str, dict[int, list[int]]] = {}
        cast_amounts: dict[tuple[str, int, str, int], int] = {}
        for ts, healer, target, skill_id, amount, apply_ts in heal_events:
            if target not in players:
                continue
            if apply_ts < start or apply_ts > last_apply + SUOMING_ROUND_TAIL_MS:
                continue
            if not (start <= ts < end):
                continue
            totals[healer] = totals.get(healer, 0) + amount
            cast_key = (healer, skill_id, target, ts // 1000)
            cast_amounts[cast_key] = cast_amounts.get(cast_key, 0) + amount

        for (healer, skill_id, _target, _sec), amount in cast_amounts.items():
            skill_hits.setdefault(healer, {}).setdefault(skill_id, []).append(amount)

        ranked = sorted(totals.items(), key=lambda x: (-x[1], meta.players[x[0]].name))
        rnd = DeadServantRound(
            index=i,
            start_ms=start,
            end_ms=end,
            start_rel=ms_hms(start, base),
            servant_count=count,
            shield_heal=[
                RankEntry(
                    pid=pid,
                    name=meta.players[pid].name,
                    xf_id=meta.players[pid].xf_id,
                    value=val,
                    extra={
                        "hits": sum(len(v) for v in skill_hits.get(pid, {}).values()),
                        "skills": skill_hits.get(pid, {}),
                    },
                )
                for pid, val in ranked
            ],
        )
        result.dead_rounds.append(rnd)

    return result


def to_api_payload(result: AsnAnalysisResult) -> dict[str, Any]:
    """兼容原远程 asn_analyze 响应结构."""
    hit: list[dict[str, dict[str, int]]] = []
    for wave in result.jiqu_waves:
        row: dict[str, dict[str, int]] = {}
        for e in wave.qte_po:
            row[e.name] = {"good": e.value, "bad": int(e.extra.get("bad", 0))}
        hit.append(row)

    hps: list[dict[str, Any]] = []
    for rnd in result.dead_rounds:
        for e in rnd.shield_heal:
            skills_raw: dict[int, list[int]] = e.extra.get("skills", {})
            skills = {
                str(skill_id): values
                for skill_id, values in skills_raw.items()
            }
            hps.append(
                {
                    "name": e.name,
                    "kungfu_id": e.xf_id,
                    "value": e.value,
                    "skills": skills,
                }
            )
        hps.append({})

    return {"data": {"hit": hit, "hps": hps}}

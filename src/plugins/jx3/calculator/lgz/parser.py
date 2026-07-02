"""柳公子 JCL 本地解析：传功轮次 + 团灭原因（低内存流式）."""

from __future__ import annotations

import gc
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .lua_table import LuaTableAnalyserToDict

MAX_JCL_BYTES = 24 * 1024 * 1024
MIN_FREE_MB = 350

BOSS = "1074160857"
TRANSFER_SKILL = 45010
TRANSFER_CAST_MS = 8000
TRANSFER_WINDOW_MS = 15000
WIPE_CLUSTER_MS = 3000
WIPE_MIN_PLAYERS = 5
TRANSFER_MIN_PLAYERS = 2
WEAPON_SLOW_MS = 8000
TRANSFER_SLOW_MS = 20000

BUFF_DISARM_BOSS = 33300
BUFF_DISARM_PLAYER = 33563
BUFF_PANSHI = 33471
BUFF_HUICHUN = 33473
BUFF_DUANMAI = 33463
BUFF_NEEDLES = (b"33300", b"33563", b"33471", b"33473", b"33463")

FAN_TEMPLATES = {"137190", "137195", "137196"}

DEF_XF = {10002, 10028, 10224, 10225, 10389}
HEAL_XF = {10026, 10242, 10243, 10533, 10626, 10698, 10756, 10448}
INNER_XF = {10014, 10026, 10062, 10080, 10081, 10176, 10242, 10243, 10533, 10698, 10821, 10448}
OUTER_XF = {10003, 10015, 10021, 10615}


def check_memory_available() -> None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            info = f.read()
        avail_kb = 0
        for line in info.splitlines():
            if line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
                break
        if avail_kb and avail_kb < MIN_FREE_MB * 1024:
            raise MemoryError(
                f"服务器可用内存不足（约 {avail_kb // 1024}MB），"
                f"请稍后再试或联系管理员（需要至少 {MIN_FREE_MB}MB）"
            )
    except FileNotFoundError:
        pass


def fix_gbk(v: str) -> str:
    if not v or all(ord(c) < 128 for c in str(v)):
        return str(v).strip('"')
    try:
        return str(v).encode("latin-1").decode("gbk").strip('"')
    except Exception:
        return str(v).strip('"')


def _decode_payload(raw: bytes) -> str:
    for enc in ("gbk", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def ms_hms(ms: int, base: int) -> str:
    s = max(0, ms - base) // 1000
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def xf_category(xf: int) -> str:
    if xf in DEF_XF:
        return "防御"
    if xf in HEAL_XF:
        return "治疗"
    if xf in INNER_XF:
        return "内功"
    if xf in OUTER_XF:
        return "外功"
    return "未知"


@dataclass
class PlayerInfo:
    pid: str
    name: str
    school: str
    xf_id: int
    xf_name: str
    xf_type: str


@dataclass
class TimelineEvent:
    time: int
    rel: str
    kind: str
    player_id: str
    player_name: str
    xf_id: int
    detail: str = ""


@dataclass
class TransferParticipant:
    player_id: str
    player_name: str
    xf_id: int
    xf_type: str
    cast_rel: str
    done_rel: str
    duration_ms: int


@dataclass
class TransferRound:
    round_index: int
    start_ms: int
    end_ms: int
    start_rel: str
    end_rel: str
    success_ms: int
    success_rel: str
    weapon_placer: PlayerInfo | None
    weapon_placed_rel: str
    weapon_placed_ms: int
    boss_disarm: PlayerInfo | None
    boss_disarm_rel: str
    boss_disarm_ms: int
    participants: list[TransferParticipant]
    type_counts: dict[str, int]
    expected_effect: str
    effect_triggered: str
    timeline: list[TimelineEvent]


@dataclass
class WipeAnalysis:
    is_wipe: bool
    wipe_rel: str
    wipe_count: int
    battle_duration_rel: str
    category: str
    detail: str
    transfer_reasons: list[str]
    damage_source: str
    damage_summary: str


@dataclass
class LGZAnalysisResult:
    base_ms: int
    battle_duration_ms: int
    server: str
    boss_name: str
    map_name: str
    rounds: list[TransferRound]
    wipe: WipeAnalysis
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class _BuffRec:
    time: int
    bid: int
    deleted: bool
    lv: int
    target: str
    source: str


class JCLLoader:
    def __init__(self) -> None:
        self.players: dict[str, PlayerInfo] = {}
        self.npcs: dict[str, dict] = {}
        self.base_ms = 0
        self.server = ""
        self.sum_time = 0
        self.disarms: list[tuple[int, str]] = []
        self.placements: list[tuple[int, str]] = []
        self.casts: list[tuple[int, str]] = []
        self.completes: list[tuple[int, str]] = []
        self.deaths: list[tuple[int, str, str]] = []
        self.buffs: list[_BuffRec] = []
        self._event_count = 0

    def _touch_time(self, t_ms: int) -> None:
        self.base_ms = t_ms if self.base_ms == 0 else min(self.base_ms, t_ms)

    def _parse_lua(self, lta: LuaTableAnalyserToDict, blob: bytes) -> dict | None:
        try:
            return lta.analyse(_decode_payload(blob), delta=1)
        except Exception:
            return None

    def _iter_lines(self, source: bytes | str) -> Any:
        if isinstance(source, str):
            with open(source, "rb") as f:
                for line in f:
                    yield line
            return
        for line in source.splitlines():
            yield line

    def load_bytes(self, raw: bytes) -> None:
        if len(raw) > MAX_JCL_BYTES:
            raise ValueError(
                f"JCL 文件过大（{len(raw) / 1024 / 1024:.1f}MB），"
                f"上限 {MAX_JCL_BYTES // 1024 // 1024}MB"
            )
        check_memory_available()
        self._load_stream(raw)

    def load_path(self, path: str) -> None:
        import os

        size = os.path.getsize(path)
        if size > MAX_JCL_BYTES:
            raise ValueError(
                f"JCL 文件过大（{size / 1024 / 1024:.1f}MB），"
                f"上限 {MAX_JCL_BYTES // 1024 // 1024}MB"
            )
        check_memory_available()
        self._load_stream(path)

    def _load_stream(self, source: bytes | str) -> None:
        lta = LuaTableAnalyserToDict()
        for line in self._iter_lines(source):
            if not line.strip():
                continue
            parts = line.split(b"\t", 5)
            if len(parts) < 6:
                continue
            et = parts[4]
            try:
                t_ms = int(parts[3])
            except ValueError:
                continue
            self._touch_time(t_ms)
            payload_blob = parts[5]

            if et == b"1":
                payload = self._parse_lua(lta, payload_blob)
                if payload and not self.server:
                    try:
                        self.server = payload["2"].split(":")[2].split("_")[1]
                        self.sum_time = int(payload.get("3") or payload["2"].split(":")[4])
                    except Exception:
                        pass
                continue

            if et == b"4":
                payload = self._parse_lua(lta, payload_blob)
                if not payload:
                    continue
                pid = str(payload["1"])
                xf = int(payload["4"])
                from src.const.jx3.kungfu import Kungfu

                kf = Kungfu.with_internel_id(xf, True)
                self.players[pid] = PlayerInfo(
                    pid=pid,
                    name=fix_gbk(payload["2"]),
                    school=str(payload["3"]),
                    xf_id=xf,
                    xf_name=kf.name or str(xf),
                    xf_type=xf_category(xf),
                )
                continue

            if et == b"8":
                payload = self._parse_lua(lta, payload_blob)
                if not payload:
                    continue
                self.npcs[str(payload["1"])] = {
                    "name": fix_gbk(payload["2"]),
                    "template": str(payload.get("3", "")),
                }
                continue

            if et == b"28":
                payload = self._parse_lua(lta, payload_blob)
                if not payload:
                    continue
                vid = str(payload.get("1", ""))
                if vid in self.players:
                    self.deaths.append((t_ms, vid, str(payload.get("2", ""))))
                    self._event_count += 1
                continue

            if et == b"13":
                if not any(n in payload_blob for n in BUFF_NEEDLES):
                    continue
                payload = self._parse_lua(lta, payload_blob)
                if not payload:
                    continue
                bid = int(payload.get("5", 0))
                if bid not in (BUFF_DISARM_BOSS, BUFF_DISARM_PLAYER, BUFF_PANSHI, BUFF_HUICHUN, BUFF_DUANMAI):
                    continue
                deleted = payload.get("2") in (True, "true")
                tgt = str(payload.get("1", ""))
                if not deleted:
                    if bid == BUFF_DISARM_BOSS:
                        self.disarms.append((t_ms, tgt))
                    elif bid == BUFF_DISARM_PLAYER:
                        self.placements.append((t_ms, tgt))
                self.buffs.append(_BuffRec(
                    time=t_ms,
                    bid=bid,
                    deleted=deleted,
                    lv=int(payload.get("9", 1)),
                    target=tgt,
                    source=str(payload.get("10", "")),
                ))
                self._event_count += 1
                continue

            if et == b"19":
                if b"45010" not in payload_blob:
                    continue
                payload = self._parse_lua(lta, payload_blob)
                if not payload or int(payload.get("2", 0)) != TRANSFER_SKILL:
                    continue
                self.casts.append((t_ms, str(payload.get("1", ""))))
                self._event_count += 1
                continue

            if et == b"21":
                if b"45010" not in payload_blob:
                    continue
                payload = self._parse_lua(lta, payload_blob)
                if not payload or int(payload.get("5", 0)) != TRANSFER_SKILL:
                    continue
                self.completes.append((t_ms, str(payload.get("1", ""))))
                self._event_count += 1

    def scan_wipe_skills(self, source: bytes | str, wipe_ms: int, victim_ids: set[str]) -> Counter[int]:
        if wipe_ms <= 0 or not victim_ids:
            return Counter()
        lta = LuaTableAnalyserToDict()
        t0 = wipe_ms - 3000
        t1 = wipe_ms + 1000
        hits: Counter[int] = Counter()
        for line in self._iter_lines(source):
            if not line.strip():
                continue
            parts = line.split(b"\t", 5)
            if len(parts) < 6 or parts[4] != b"21":
                continue
            try:
                t_ms = int(parts[3])
            except ValueError:
                continue
            if t_ms < t0 or t_ms > t1:
                continue
            payload = self._parse_lua(lta, parts[5])
            if not payload:
                continue
            tgt = str(payload.get("2", ""))
            if tgt in victim_ids:
                hits[int(payload.get("5", 0))] += 1
        return hits

    def player(self, pid: str, anonymous: bool = False) -> PlayerInfo:
        if pid in self.players:
            p = self.players[pid]
            if anonymous:
                return PlayerInfo(p.pid, "匿名玩家", p.school, p.xf_id, p.xf_name, p.xf_type)
            return p
        return PlayerInfo(pid, "未知", "?", 0, "?", "未知")

    def is_fan_entity(self, eid: str) -> bool:
        if eid in self.npcs:
            return self.npcs[eid].get("template") in FAN_TEMPLATES
        return eid.startswith("1074176") and eid != BOSS

    def entity_name(self, eid: str, anonymous: bool = False) -> str:
        if eid in self.players:
            return self.player(eid, anonymous).name
        if self.is_fan_entity(eid):
            return f"裂风扇子({eid[-4:]})"
        if eid in self.npcs:
            n = self.npcs[eid]
            nm = n.get("name") or ""
            if nm.strip():
                return nm
        if eid == BOSS:
            return "柳公子"
        if eid == "0":
            return "环境"
        return f"NPC({eid[-6:]})"


def player_label(loader: JCLLoader, pid: str, anonymous: bool = False) -> str:
    p = loader.player(pid, anonymous)
    return f"{p.name} · {p.xf_name} · {p.pid}"


def skill_display_name(skill_id: int) -> str:
    try:
        from src.utils.database.attributes import TabCache

        _, name = TabCache.get_icon_for_skill(skill_id)
        return name if name != "未知" else f"技能{skill_id}"
    except Exception:
        return f"技能{skill_id}"


def _infer_effect(weapon_type: str, total_count: int) -> tuple[str, str]:
    rules = {
        "外功": "破甲",
        "内功": "封脉",
        "防御": "全场磐石",
        "治疗": "全场回春",
    }
    effect = rules.get(weapon_type, "未知效果")
    if total_count >= TRANSFER_MIN_PLAYERS:
        return f"应触发 {effect}", "已达标"
    return f"需≥{TRANSFER_MIN_PLAYERS}人传功（实际{total_count}）", "未触发"


def _verify_effect(loader: JCLLoader, start_ms: int, end_ms: int, weapon_type: str, triggered: str) -> str:
    if triggered != "已达标":
        return triggered
    t_start = start_ms
    t_end = end_ms + 25000
    panshi = huichun = duanmai = 0
    for rec in loader.buffs:
        if not (t_start <= rec.time <= t_end):
            continue
        if rec.deleted:
            continue
        if rec.bid == BUFF_PANSHI and rec.lv >= 2:
            panshi += 1
        if rec.bid == BUFF_HUICHUN:
            huichun += 1
        if rec.bid == BUFF_DUANMAI and rec.source == BOSS:
            duanmai += 1
    checks = {
        "防御": panshi > 0,
        "治疗": huichun > 0,
        "内功": duanmai > 0,
        "外功": False,
    }
    if checks.get(weapon_type):
        return "JCL已验证"
    if weapon_type == "外功":
        return "已达标（破甲无独立buff标记）"
    return "已达标但未在JCL中检测到对应buff"


def build_transfer_rounds(loader: JCLLoader, anonymous: bool) -> list[TransferRound]:
    base = loader.base_ms
    disarms = loader.disarms
    placements = loader.placements
    casts = loader.casts
    completes = sorted(loader.completes)

    rounds_raw: list[list[tuple[int, str]]] = []
    if completes:
        cur = [completes[0]]
        for item in completes[1:]:
            if item[0] - cur[-1][0] <= TRANSFER_WINDOW_MS:
                cur.append(item)
            else:
                rounds_raw.append(cur)
                cur = [item]
        rounds_raw.append(cur)

    result: list[TransferRound] = []
    for idx, comp_group in enumerate(rounds_raw, 1):
        pids = list(dict.fromkeys(pid for _, pid in comp_group))
        comp_sorted = sorted(comp_group, key=lambda x: x[0])
        first_comp = comp_sorted[0][0]
        last_comp = comp_sorted[-1][0]
        round_casts = [
            (t, pid) for t, pid in casts
            if first_comp - 12000 <= t <= last_comp + 500
        ]
        start_ms = min((t for t, _ in round_casts), default=first_comp)
        end_ms = last_comp
        cast_map = {pid: t for t, pid in round_casts}
        complete_map = {pid: t for t, pid in comp_sorted}

        placement = max(((t, pid) for t, pid in placements if t < start_ms), key=lambda x: x[0], default=None)
        disarm = max(((t, pid) for t, pid in disarms if t < start_ms), key=lambda x: x[0], default=None)

        weapon_placer = loader.player(placement[1], anonymous) if placement else None
        boss_disarm_p = loader.player(disarm[1], anonymous) if disarm else None
        placement_ms = placement[0] if placement else 0
        disarm_ms = disarm[0] if disarm else 0

        participants: list[TransferParticipant] = []
        for pid in pids:
            pi = loader.player(pid, anonymous)
            ct = cast_map.get(pid, start_ms)
            dt = complete_map[pid]
            participants.append(
                TransferParticipant(
                    player_id=pid,
                    player_name=pi.name,
                    xf_id=pi.xf_id,
                    xf_type=pi.xf_type,
                    cast_rel=ms_hms(ct, base),
                    done_rel=ms_hms(dt, base),
                    duration_ms=dt - ct,
                )
            )

        type_counts = Counter(p.xf_type for p in participants)
        weapon_type = weapon_placer.xf_type if weapon_placer else "未知"
        expected, triggered = _infer_effect(weapon_type, len(participants))
        verified = _verify_effect(loader, start_ms, end_ms, weapon_type, triggered)

        success_ms = comp_sorted[TRANSFER_MIN_PLAYERS - 1][0] if len(comp_sorted) >= TRANSFER_MIN_PLAYERS else 0
        success_rel = ms_hms(success_ms, base) if success_ms else "—"

        timeline: list[TimelineEvent] = []
        if disarm:
            timeline.append(TimelineEvent(
                disarm[0], ms_hms(disarm[0], base), "缴械点名",
                disarm[1], boss_disarm_p.name if boss_disarm_p else "", boss_disarm_p.xf_id if boss_disarm_p else 0,
                player_label(loader, disarm[1], anonymous),
            ))
        if placement:
            timeline.append(TimelineEvent(
                placement[0], ms_hms(placement[0], base), "放置武器",
                placement[1], weapon_placer.name if weapon_placer else "", weapon_placer.xf_id if weapon_placer else 0,
                player_label(loader, placement[1], anonymous),
            ))
        completed_pids = set(pids)
        for t, pid in sorted(round_casts, key=lambda x: x[0]):
            pi = loader.player(pid, anonymous)
            label = player_label(loader, pid, anonymous)
            if pid in completed_pids:
                timeline.append(TimelineEvent(
                    cast_map[pid], ms_hms(cast_map[pid], base), "传功开始",
                    pid, pi.name, pi.xf_id, label,
                ))
                dt = complete_map[pid]
                is_effect = (
                    len(comp_sorted) >= TRANSFER_MIN_PLAYERS
                    and pid == comp_sorted[TRANSFER_MIN_PLAYERS - 1][1]
                )
                timeline.append(TimelineEvent(
                    dt, ms_hms(dt, base), "传功生效" if is_effect else "传功完成",
                    pid, pi.name, pi.xf_id, label,
                ))
            else:
                timeline.append(TimelineEvent(
                    cast_map[pid], ms_hms(cast_map[pid], base), "传功开始",
                    pid, pi.name, pi.xf_id, label,
                ))
                timeline.append(TimelineEvent(
                    t + TRANSFER_CAST_MS, ms_hms(t + TRANSFER_CAST_MS, base), "传功中断",
                    pid, pi.name, pi.xf_id, label,
                ))
        timeline.sort(key=lambda x: x.time)

        result.append(
            TransferRound(
                round_index=idx,
                start_ms=start_ms,
                end_ms=end_ms,
                start_rel=ms_hms(start_ms, base),
                end_rel=ms_hms(end_ms, base),
                success_ms=success_ms,
                success_rel=success_rel,
                weapon_placer=weapon_placer,
                weapon_placed_rel=ms_hms(placement[0], base) if placement else "—",
                weapon_placed_ms=placement_ms,
                boss_disarm=boss_disarm_p,
                boss_disarm_rel=ms_hms(disarm[0], base) if disarm else "—",
                boss_disarm_ms=disarm_ms,
                participants=participants,
                type_counts=dict(type_counts),
                expected_effect=expected,
                effect_triggered=verified,
                timeline=timeline,
            )
        )
    return result


def _transfer_fail_reasons(rnd: TransferRound) -> list[str]:
    reasons: list[str] = []
    n = len(rnd.participants)
    if n < TRANSFER_MIN_PLAYERS:
        reasons.append("传功人少了")
    if rnd.boss_disarm_ms and rnd.weapon_placed_ms:
        if rnd.weapon_placed_ms - rnd.boss_disarm_ms > WEAPON_SLOW_MS:
            reasons.append("武器放慢了")
    if rnd.weapon_placed_ms and rnd.start_ms and rnd.weapon_placed_ms > rnd.start_ms:
        reasons.append("武器放慢了")
    if rnd.weapon_placed_ms and rnd.success_ms:
        if rnd.success_ms - rnd.weapon_placed_ms > TRANSFER_SLOW_MS:
            reasons.append("传功慢了")
    elif rnd.weapon_placed_ms and n < TRANSFER_MIN_PLAYERS and rnd.end_ms:
        if rnd.end_ms - rnd.weapon_placed_ms > TRANSFER_SLOW_MS:
            reasons.append("传功慢了")
    return list(dict.fromkeys(reasons))


def _find_wipe_round(wipe_ms: int, rounds: list[TransferRound]) -> TransferRound | None:
    for rnd in rounds:
        phase_start = (rnd.boss_disarm_ms or rnd.weapon_placed_ms or rnd.start_ms) - 5000
        phase_end = rnd.end_ms + TRANSFER_WINDOW_MS
        if phase_start <= wipe_ms <= phase_end:
            return rnd
    return None


def analyze_wipe(
    loader: JCLLoader,
    anonymous: bool,
    rounds: list[TransferRound],
    source: bytes | str | None = None,
) -> WipeAnalysis:
    base = loader.base_ms
    last_t = loader.deaths[-1][0] if loader.deaths else base
    duration = loader.sum_time or max(0, last_t - base)

    player_deaths: list[dict] = []
    for t_ms, vid, kid in loader.deaths:
        player_deaths.append({
            "time": t_ms,
            "rel": ms_hms(t_ms, base),
            "victim_id": vid,
            "victim": loader.entity_name(vid, anonymous),
            "killer_id": kid,
            "killer": loader.entity_name(kid, anonymous),
        })

    cluster: list[dict] = []
    wipe_rel = "—"
    wipe_ms = 0
    if player_deaths:
        sorted_d = sorted(player_deaths, key=lambda x: x["time"])
        best: list[dict] = []
        for anchor in sorted_d:
            window = [d for d in sorted_d if anchor["time"] <= d["time"] <= anchor["time"] + WIPE_CLUSTER_MS]
            if len(window) > len(best):
                best = window
        cluster = best
        if cluster:
            wipe_rel = cluster[0]["rel"]
            wipe_ms = cluster[0]["time"]

    is_wipe = len(cluster) >= WIPE_MIN_PLAYERS

    if not is_wipe:
        if len(player_deaths) == 0:
            return WipeAnalysis(
                is_wipe=False, wipe_rel="—", wipe_count=0,
                battle_duration_rel=ms_hms(base + duration, base),
                category="未团灭", detail="无玩家重伤记录",
                transfer_reasons=[], damage_source="—", damage_summary="—",
            )
        return WipeAnalysis(
            is_wipe=False, wipe_rel=wipe_rel, wipe_count=len(cluster),
            battle_duration_rel=ms_hms(base + duration, base),
            category="未团灭",
            detail=f"有 {len(player_deaths)} 次重伤，未形成 {WIPE_MIN_PLAYERS} 人以上的团灭簇",
            transfer_reasons=[], damage_source="—", damage_summary="—",
        )

    victim_ids = {d["victim_id"] for d in cluster}
    skill_on_victims: Counter[int] = Counter()
    if source is not None:
        skill_on_victims = loader.scan_wipe_skills(source, wipe_ms, victim_ids)

    killers = Counter(d["killer"] for d in cluster)
    top_killer, _ = killers.most_common(1)[0]
    if skill_on_victims:
        top_skill_id = skill_on_victims.most_common(1)[0][0]
        damage_source = skill_display_name(top_skill_id)
        if damage_source.startswith("技能"):
            damage_source = top_killer
    else:
        damage_source = top_killer

    t_first = cluster[0]["rel"]
    t_last = cluster[-1]["rel"]
    time_range = t_first if t_first == t_last else f"{t_first} ~ {t_last}"
    if len(killers) == 1:
        damage_summary = f"{len(cluster)} 人在 {time_range} 被 {top_killer} 击杀"
    else:
        parts = "、".join(f"{k}({n}人)" for k, n in killers.most_common(3))
        damage_summary = f"{len(cluster)} 人在 {time_range} 团灭，主要来源：{parts}"

    wipe_round = _find_wipe_round(wipe_ms, rounds)
    is_transfer_wipe = False
    transfer_reasons: list[str] = []

    if wipe_round:
        transfer_reasons = _transfer_fail_reasons(wipe_round)
        if transfer_reasons:
            is_transfer_wipe = True
        elif wipe_ms <= wipe_round.end_ms + 5000 and len(wipe_round.participants) < TRANSFER_MIN_PLAYERS:
            is_transfer_wipe = True
            transfer_reasons = ["传功人少了"]
        elif wipe_round.effect_triggered == "未触发" and wipe_ms <= wipe_round.end_ms + TRANSFER_WINDOW_MS:
            is_transfer_wipe = True
            transfer_reasons = _transfer_fail_reasons(wipe_round) or ["传功人少了"]

    if is_transfer_wipe:
        reason_text = "、".join(transfer_reasons) if transfer_reasons else "传功未完成"
        detail = f"第 {wipe_round.round_index if wipe_round else '?'} 轮传功阶段团灭：{reason_text}"
        category = "传功团灭"
    else:
        category = "非传功团灭"
        detail = damage_source

    return WipeAnalysis(
        is_wipe=True,
        wipe_rel=wipe_rel,
        wipe_count=len(cluster),
        battle_duration_rel=ms_hms(base + duration, base),
        category=category,
        detail=detail,
        transfer_reasons=transfer_reasons,
        damage_source=damage_source,
        damage_summary=damage_summary,
    )


def parse_lgz_jcl(raw: bytes, file_name: str = "", anonymous: bool = False) -> LGZAnalysisResult:
    return _parse_lgz(source=raw, file_name=file_name, anonymous=anonymous)


def parse_lgz_jcl_path(path: str, file_name: str = "", anonymous: bool = False) -> LGZAnalysisResult:
    return _parse_lgz(source=path, file_name=file_name, anonymous=anonymous)


def _parse_lgz(source: bytes | str, file_name: str, anonymous: bool) -> LGZAnalysisResult:
    check_memory_available()
    loader = JCLLoader()
    if isinstance(source, str):
        loader.load_path(source)
    else:
        loader.load_bytes(source)

    if not loader.players:
        raise ValueError("无法识别玩家信息，请确认是否为有效的柳公子 JCL")

    rounds = build_transfer_rounds(loader, anonymous)
    wipe = analyze_wipe(loader, anonymous, rounds, source=source)

    loader.buffs.clear()
    loader.disarms.clear()
    loader.placements.clear()
    loader.casts.clear()
    loader.completes.clear()
    loader.deaths.clear()
    gc.collect()

    map_name, boss_name = "?", "柳公子"
    if file_name:
        stem = file_name[4:] if file_name.upper().startswith("LGZ-") else file_name
        parts = stem.rsplit(".", 1)[0].split("-")
        if len(parts) >= 8:
            map_name = parts[6]
            boss_name = parts[7]

    return LGZAnalysisResult(
        base_ms=loader.base_ms,
        battle_duration_ms=loader.sum_time,
        server=loader.server,
        boss_name=boss_name,
        map_name=map_name,
        rounds=rounds,
        wipe=wipe,
        meta={"player_count": len(loader.players), "event_count": loader._event_count},
    )

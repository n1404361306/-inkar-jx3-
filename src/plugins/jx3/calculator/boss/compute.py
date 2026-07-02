"""通用 Boss 全程 DPS/HPS：流式喂入 jx3bla CombatTracker."""

from __future__ import annotations

import gc
import sys
from dataclasses import dataclass, field
from typing import Any

JX3BLA_ROOT = "/root/jx3bla"
if JX3BLA_ROOT not in sys.path:
    sys.path.insert(0, JX3BLA_ROOT)

from data.DataContent import OverallData, SingleDataBuff, SingleDataSkill  # noqa: E402
from replayer.CombatTracker import CombatTracker  # noqa: E402
from tools.Functions import checkOccDetailByBuff, checkOccDetailBySkill  # noqa: E402

from .parser import BossJCLMeta, BossPlayerInfo, battle_time_sec, iter_boss_combat_events, scan_boss_meta

_OCC_REFINE_SCHOOLS = frozenset({"1", "2", "3", "4", "5", "6", "7", "10", "21", "22", "212"})
_OCC_BUFF_SCHOOLS = frozenset({"1", "3", "10", "21"})


class _MockBh:
    badPeriodDpsLog: list = []
    badPeriodHealerLog: list = []
    mainTargets: set = set()

    def __init__(self, battle_ms: int) -> None:
        self._battle_ms = max(battle_ms, 1000)

    def sumTime(self, _kind: str) -> int:
        return self._battle_ms


@dataclass
class BossPlayerStat:
    pid: str
    name: str
    xf_id: int
    total_damage: int = 0
    dps: int = 0
    total_heal: int = 0
    hps: int = 0
    damage_share: float = 0.0


@dataclass
class BossFightResult:
    meta: BossJCLMeta
    battle_time: float
    players: list[BossPlayerStat] = field(default_factory=list)
    team_dps: int = 0
    team_hps: int = 0


def _build_jx3_info(meta: BossJCLMeta) -> OverallData:
    info = OverallData()
    info.server = meta.server
    info.boss = meta.boss_name
    info.map = meta.dungeon
    info.skill = {}
    for pid, p in meta.players.items():
        info.addPlayer(pid, p.name, p.school)
        info.player[pid].xf = str(p.xf_id)
    for nid in meta.npc_ids:
        info.addNPC(nid, "NPC")
    return info


def _jcl_item(ts: int, et: str, payload: dict[str, Any]) -> list[Any]:
    return ["0", "0", "0", str(ts), et, payload]


def _refine_occ(path: str, meta: BossJCLMeta, occ: dict[str, str]) -> None:
    assert meta.battle is not None
    for ts, et, payload in iter_boss_combat_events(path, meta.battle):
        if et == "21":
            caster = str(payload.get("1", ""))
            if caster not in occ:
                continue
            school = occ[caster]
            if school in _OCC_REFINE_SCHOOLS and int(payload.get("4") or 0) == 1:
                sk = SingleDataSkill()
                sk.setByJcl(_jcl_item(ts, et, payload))
                occ[caster] = checkOccDetailBySkill(school, sk.id, sk.damageEff)
        elif et == "13":
            caster = str(payload.get("10", payload.get("1", "")))
            if caster not in occ:
                continue
            school = occ[caster]
            if school in _OCC_BUFF_SCHOOLS:
                sk = SingleDataBuff()
                sk.setByJcl(_jcl_item(ts, et, payload))
                occ[caster] = checkOccDetailByBuff(school, sk.id)


def compute_boss_fight(path: str, file_name: str) -> BossFightResult:
    meta = scan_boss_meta(path, file_name)
    assert meta.battle is not None
    bt = battle_time_sec(meta.battle)

    occ_detail: dict[str, str] = {pid: p.school for pid, p in meta.players.items()}
    _refine_occ(path, meta, occ_detail)

    info = _build_jx3_info(meta)
    base_attrib = {pid: None for pid in info.player}
    for pid in info.player:
        if pid not in occ_detail:
            occ_detail[pid] = info.player[pid].occ or "0"
    battle_ms = int(meta.battle.end_ms - meta.battle.start_ms)
    tracker = CombatTracker(info, _MockBh(battle_ms), occ_detail, {}, {}, "0", base_attrib)

    for ts, et, payload in iter_boss_combat_events(path, meta.battle):
        if et == "21":
            ev = SingleDataSkill()
            ev.setByJcl(_jcl_item(ts, et, payload))
            tracker.recordSkill(ev)
        elif et == "13":
            ev = SingleDataBuff()
            ev.setByJcl(_jcl_item(ts, et, payload))
            tracker.recordBuff(ev)

    tracker.export(battle_ms, battle_ms, battle_ms, {})

    players: list[BossPlayerStat] = []
    for pid, p in meta.players.items():
        nd = tracker.ndps["player"].get(pid, {})
        hp = tracker.hps["player"].get(pid, {})
        total_dmg = int(nd.get("sum") or 0)
        total_heal = int(hp.get("sum") or 0)
        players.append(
            BossPlayerStat(
                pid=pid,
                name=p.name,
                xf_id=p.xf_id,
                total_damage=total_dmg,
                dps=int(nd.get("dps") or 0),
                total_heal=total_heal,
                hps=int(hp.get("hps") or 0),
            )
        )

    team_dmg = sum(p.total_damage for p in players)
    for p in players:
        p.damage_share = round(p.total_damage / team_dmg * 100, 2) if team_dmg else 0.0

    result = BossFightResult(
        meta=meta,
        battle_time=bt,
        players=sorted(players, key=lambda x: -x.dps),
        team_dps=int(tracker.ndps.get("sum") or 0),
        team_hps=int(tracker.hps.get("sum") or 0),
    )

    del tracker, info, occ_detail
    gc.collect()
    return result

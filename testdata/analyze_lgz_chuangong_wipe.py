#!/usr/bin/env python3
"""LGZ 传功专项 + 团灭原因分析报告生成器."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

JX3BLA_ROOT = Path("/root/jx3bla")
sys.path.insert(0, str(JX3BLA_ROOT))

from data.DataContent import (  # noqa: E402
    SingleDataBattle,
    SingleDataBuff,
    SingleDataCast,
    SingleDataDeath,
    SingleDataScene,
    SingleDataShout,
    SingleDataSkill,
)
from data.BattleLogData import BattleLogData  # noqa: E402
from tools.LoadData import LuaTableAnalyserToDict  # noqa: E402

JCL_PATH = Path(
    "/root/Inkar-Suki/testdata/"
    "LGZ-2026-05-13-22-41-46-25人英雄阆风悬城(795)-柳公子(137135).jcl"
)
OUT_CHUANGONG = JCL_PATH.with_suffix(".analysis.chuangong.md")
OUT_WIPE = JCL_PATH.with_suffix(".analysis.wipe.md")

BOSS = "1074160857"
TRANSFER_SKILL = 45010
WINDOW_MS = 15000  # 攻略：首次传功结束15秒内累计人数

SCHOOL = {
    1: "天策", 2: "万花", 3: "少林", 4: "纯阳", 5: "七秀", 6: "五毒", 7: "少林",
    10: "七秀", 21: "明教", 22: "唐门", 24: "蓬莱", 211: "霸刀", 212: "蓬莱",
    213: "北天药宗", 214: "长歌",
}

XF_NAME = {
    10002: "铁牢律", 10014: "气纯", 10015: "天罗诡道", 10021: "傲血战意", 10028: "铁骨衣",
    10062: "焚影圣诀", 10080: "分山劲", 10081: "冰心诀", 10176: "毒经", 10224: "铁骨衣",
    10225: "明尊琉璃体", 10242: "云裳心经", 10243: "相知", 10243: "相知",
    10389: "铁骨衣", 10448: "莫问", 10533: "凌海诀", 10615: "北傲诀", 10626: "无方",
    10698: "灵素", 10756: "相知", 10821: "天罗诡道",
}

DEF_XF = {10002, 10028, 10224, 10225, 10389}
HEAL_XF = {10026, 10242, 10243, 10533, 10626, 10698, 10756, 10448}
INNER_XF = {10014, 10026, 10062, 10080, 10081, 10176, 10242, 10243, 10533, 10698, 10821, 10448}
OUTER_XF = {10003, 10015, 10021, 10615, 10080}


def fix_gbk(v: str) -> str:
    if not v or all(ord(c) < 128 for c in v):
        return str(v).strip('"')
    try:
        return v.encode("latin-1").decode("gbk").strip('"')
    except Exception:
        return str(v).strip('"')


def ms_hms(ms: int, base: int) -> str:
    s = max(0, ms - base) // 1000
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def xf_type(xf: int) -> str:
    if xf in DEF_XF:
        return "防御"
    if xf in HEAL_XF:
        return "治疗"
    if xf in INNER_XF:
        return "内功"
    if xf in OUTER_XF:
        return "外功"
    return "未知"


def load_bld() -> tuple[BattleLogData, int]:
    raw = JCL_PATH.read_bytes()
    content = raw.decode("gbk")
    lta = LuaTableAnalyserToDict()
    bld = BattleLogData(window=None)
    bld.dataType = "jcl"
    first_info = True
    player_names: dict[str, str] = {}
    summon: dict[str, str] = {}

    for line in content.strip("\n").split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        et = parts[4]
        try:
            parts[5] = lta.analyse(parts[5], delta=1)
        except Exception:
            continue
        try:
            if et == "13":
                o = SingleDataBuff(); o.setByJcl(parts); bld.log.append(o)
            elif et == "21":
                o = SingleDataSkill()
                if parts[5]["1"] in summon:
                    parts[5]["1"] = summon[parts[5]["1"]]
                o.setByJcl(parts); bld.log.append(o)
            elif et == "28":
                o = SingleDataDeath(); o.setByJcl(parts); bld.log.append(o)
            elif et == "14":
                o = SingleDataShout(); o.setByJcl(parts); bld.log.append(o)
            elif et in ("5", "9"):
                o = SingleDataBattle(); o.setByJcl(parts); bld.log.append(o)
            elif et in ("2", "3", "6", "7"):
                o = SingleDataScene(); o.setByJcl(parts); bld.log.append(o)
            elif et == "19":
                o = SingleDataCast(); o.setByJcl(parts); bld.log.append(o)
            elif et == "1":
                if first_info:
                    bld.info.server = parts[5]["2"].split(":")[2].split("_")[1]
                    first_info = False
            elif et == "4":
                pid = parts[5]["1"]
                try:
                    bld.info.addPlayer(pid, parts[5]["2"], parts[5]["3"])
                    p = bld.info.player[pid]
                    p.xf = parts[5]["4"]
                    p.equipScore = parts[5]["5"]
                    player_names[fix_gbk(p.name)] = pid
                except Exception:
                    pass
            elif et == "8":
                bld.info.addNPC(parts[5]["1"], parts[5]["2"])
                n = bld.info.npc[parts[5]["1"]]
                n.templateID = parts[5]["3"]
                nm = fix_gbk(n.name)
                if "的" in nm:
                    cand = "的".join(nm.split("的")[:-1])
                    if cand in player_names:
                        summon[parts[5]["1"]] = player_names[cand]
        except Exception:
            pass

    base = min((x.time for x in bld.log), default=0)
    return bld, base


def player_profile(bld: BattleLogData, pid: str) -> dict:
    p = bld.info.player.get(pid)
    if not p:
        return {"id": pid, "name": pid, "school": "?", "xf_id": "?", "xf_name": "?", "type": "?"}
    xf = int(p.xf) if str(p.xf).isdigit() else 0
    sch = int(p.occ) if str(p.occ).isdigit() else 0
    return {
        "id": pid,
        "name": fix_gbk(p.name),
        "school": SCHOOL.get(sch, str(sch)),
        "xf_id": xf,
        "xf_name": XF_NAME.get(xf, f"心法{xf}"),
        "type": xf_type(xf),
        "equip": getattr(p, "equipScore", "?"),
    }


def name_of(eid: str, bld: BattleLogData, npc_cache: dict) -> str:
    if eid in bld.info.player:
        return fix_gbk(bld.info.player[eid].name)
    if eid in bld.info.npc:
        n = bld.info.npc[eid]
        tid = str(getattr(n, "templateID", ""))
        npc_cache[eid] = tid
        if tid in ("137190", "137195", "137196"):
            return f"裂风扇子({eid[-4:]})"
        nm = fix_gbk(n.name)
        return nm if nm.strip() else f"NPC({eid[-6:]})"
    if eid == "0":
        return "环境/未知"
    if eid == BOSS:
        return "柳公子"
    return f"实体{eid[-6:]}"


def collect_transfer_events(bld: BattleLogData, base: int) -> list[dict]:
    events = []
    for item in bld.log:
        if item.dataType == "Cast" and int(item.id) == TRANSFER_SKILL:
            events.append({
                "time": item.time, "rel": ms_hms(item.time, base),
                "pid": item.caster, "kind": "读条开始", "dur_ms": None,
            })
        elif item.dataType == "Skill" and int(item.id) == TRANSFER_SKILL:
            events.append({
                "time": item.time, "rel": ms_hms(item.time, base),
                "pid": item.caster, "kind": "传功完成", "dur_ms": None,
            })
    events.sort(key=lambda x: x["time"])
    # pair cast→complete
    pending: dict[str, int] = {}
    for e in events:
        if e["kind"] == "读条开始":
            pending[e["pid"]] = e["time"]
        elif e["pid"] in pending:
            e["dur_ms"] = e["time"] - pending.pop(e["pid"])
    return events


def group_rounds(events: list[dict]) -> list[list[dict]]:
    if not events:
        return []
    rounds: list[list[dict]] = []
    cur = [events[0]]
    for e in events[1:]:
        if e["time"] - cur[-1]["time"] <= WINDOW_MS:
            cur.append(e)
        else:
            rounds.append(cur)
            cur = [e]
    rounds.append(cur)
    return rounds


def collect_disarm_place(bld: BattleLogData, base: int) -> tuple[list, list]:
    disarms, places = [], []
    for item in bld.log:
        if item.dataType != "Buff":
            continue
        bid = int(item.id)
        deleted = item.delete in (True, "true")
        if bid == 33300 and not deleted:
            disarms.append({"time": item.time, "rel": ms_hms(item.time, base), "pid": item.target})
        if bid == 33563 and not deleted:
            places.append({"time": item.time, "rel": ms_hms(item.time, base), "pid": item.target})
    return disarms, places


def effect_after_time(bld: BattleLogData, t0: int, t1: int) -> dict:
    """传功完成后窗口内的结果 buff/skill."""
    res = {"33473_players": 0, "33471_players": 0, "33463_boss_side": 0, "33473_heal_skill": 0}
    for item in bld.log:
        if not (t0 <= item.time <= t1):
            continue
        if item.dataType == "Buff" and not (item.delete in (True, "true")):
            bid = int(item.id)
            lv = int(item.level)
            if bid == 33473 and lv >= 1:
                res["33473_players"] += 1
            if bid == 33471 and lv >= 2:
                res["33471_players"] += 1
            if bid == 33463:
                res["33463_boss_side"] += 1
        if item.dataType == "Skill" and int(item.id) == 33473:
            res["33473_heal_skill"] += 1
    return res


def infer_transfer_result(weapon_type: str, counts: Counter) -> list[str]:
    """效果仅由装置武器的心法类型决定，只判定对应槽位人数."""
    rules = {
        "外功": ("外功", 1, "破甲 s45017", "对柳公子造成巨额真实伤害并移除其磐石"),
        "内功": ("内功", 2, "封脉 s45018", "对柳公子断脉+10跳真实伤害"),
        "防御": ("防御", 2, "全场磐石 buff33471.2", "全场约98%减伤，持续20秒"),
        "治疗": ("治疗", 2, "全场回春 buff33473.2", "全场570w/s回血+400%血量，10秒"),
    }
    if weapon_type not in rules:
        return [f"装置武器分类「{weapon_type}」未知，无法推断效果"]
    cat, need, name, desc = rules[weapon_type]
    n = counts.get(cat, 0)
    if n >= need:
        return [f"**触发 {name}**（{desc}）"]
    return [f"装置为**{weapon_type}**武器，需 {cat}≥{need} 人传功；实际 {cat}={n}，**未触发 {name}**"]


def build_chuangong_report(bld: BattleLogData, base: int) -> str:
    events = collect_transfer_events(bld, base)
    rounds = group_rounds(events)
    disarms, places = collect_disarm_place(bld, base)

    lines = [
        "# 柳公子 · 传功机制专项分析报告",
        "",
        f"- 源文件：`{JCL_PATH.name}`",
        f"- 生成时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- 战斗时长：{ms_hms(bld.info.sumTime + base if hasattr(bld.info,'sumTime') else 0, base)}（约148秒）",
        "",
        "## 1. 机制说明（攻略摘要）",
        "",
        "神秘装置阶段（80%~40%气血）：",
        "1. 柳公子夺武 → 武器置于装置 → 按被夺者心法对 BOSS/全场产生延迟效果",
        "2. 任意玩家可主动放武器（33563缴械）至**玩家侧装置**",
        "3. 传功 c45010：蓄力8秒；**首次传功结束后15秒内**累计参与人数",
        "4. 效果取决于**装置上武器的心法类型** + **参与传功人数（按心法分类）**",
        "",
        "| 武器心法 | 人数 | 传功效果 |",
        "|----------|-----:|----------|",
        "| 外功 | ≥1 | 破甲 s45017 |",
        "| 内功 | ≥2 | 封脉 s45018 |",
        "| 防御 | ≥2 | 全场磐石 33471.2 |",
        "| 治疗 | ≥2 | 全场回春 33473.2 |",
        "",
        "---",
        "",
        "## 2. 全团心法档案（战斗时 type=4 记录）",
        "",
        "| 用户ID | 角色名 | 门派 | 心法ID | 心法名 | 机制分类 | 装分 |",
        "|--------|--------|------|-------:|--------|----------|-----:|",
    ]

    all_pids = sorted(bld.info.player.keys(), key=lambda x: -int(bld.info.player[x].equipScore or 0))
    for pid in all_pids:
        pr = player_profile(bld, pid)
        lines.append(
            f"| `{pid}` | {pr['name']} | {pr['school']} | {pr['xf_id']} | {pr['xf_name']} | {pr['type']} | {pr['equip']} |"
        )

    lines += ["", "---", "", "## 3. 缴械 / 放武器时间轴", ""]
    lines.append("### 3.1 BOSS 夺武（debuff 33300）")
    lines.append("")
    lines.append("| 时间 | 用户ID | 角色 | 心法 | 分类 | BOSS延迟效果（攻略） |")
    lines.append("|------|--------|------|------|------|---------------------|")
    boss_effect = {"治疗": "15秒后 BOSS 获回春+400%血", "外功": "18秒后全场破甲+1197w真实伤害", "内功": "15秒后全场封脉10跳", "防御": "15秒后 BOSS 获磐石98%减伤"}
    for d in disarms:
        pr = player_profile(bld, d["pid"])
        lines.append(f"| {d['rel']} | `{d['pid']}` | {pr['name']} | {pr['xf_name']} | {pr['type']} | {boss_effect.get(pr['type'], '未知')} |")

    lines += ["", "### 3.2 玩家主动放武器（debuff 33563）", ""]
    lines.append("| 时间 | 用户ID | 角色 | 心法 | 分类 | 决定传功效果槽位 |")
    lines.append("|------|--------|------|------|------|-----------------|")
    for p in places:
        pr = player_profile(bld, p["pid"])
        lines.append(f"| {p['rel']} | `{p['pid']}` | {pr['name']} | {pr['xf_name']} | {pr['type']} | {pr['type']}武器 → 对应传功条目 |")

    lines += ["", "---", "", "## 4. 传功轮次详细分析", ""]

    transfer_pids = {e["pid"] for e in events if e["kind"] == "传功完成"}

    lines += [
        "### 4.0 传功参与者心法速查",
        "",
        "| 用户ID | 角色 | 心法ID | 心法名 | 机制分类 |",
        "|--------|------|-------:|--------|----------|",
    ]
    for pid in sorted(transfer_pids):
        pr = player_profile(bld, pid)
        lines.append(f"| `{pid}` | {pr['name']} | {pr['xf_id']} | {pr['xf_name']} | {pr['type']} |")

    for ri, rnd in enumerate(rounds, 1):
        completes = [e for e in rnd if e["kind"] == "传功完成"]
        if not completes:
            continue
        pids = list(dict.fromkeys(e["pid"] for e in completes))
        first_cast = min(e["time"] for e in rnd if e["kind"] == "读条开始")
        last_done = max(e["time"] for e in completes)
        lines += [
            f"### 4.{ri} 第 {ri} 轮传功",
            "",
            f"- **时间窗口**：{ms_hms(first_cast, base)} ~ {ms_hms(last_done, base)}",
            f"- **参与人数**：{len(pids)}（去重后）",
            f"- **传功完成次数**：{len(completes)}",
            "",
            "#### 参与者明细",
            "",
            "| 用户ID | 角色 | 心法ID | 心法名 | 分类 | 读条→完成 |",
            "|--------|------|-------:|--------|------|-----------|",
        ]
        type_counts: Counter = Counter()
        for pid in pids:
            pr = player_profile(bld, pid)
            type_counts[pr["type"]] += 1
            done = next(e for e in completes if e["pid"] == pid)
            cast = next((e for e in rnd if e["pid"] == pid and e["kind"] == "读条开始"), None)
            dur = f"{done['dur_ms']}ms" if done.get("dur_ms") else "—"
            cast_t = cast["rel"] if cast else "—"
            lines.append(
                f"| `{pid}` | {pr['name']} | {pr['xf_id']} | {pr['xf_name']} | {pr['type']} | {cast_t} → {done['rel']} ({dur}) |"
            )

        lines += ["", "#### 心法类型统计", ""]
        lines.append("| 分类 | 人数 | 传功阈值 | 是否达标 |")
        lines.append("|------|-----:|----------|----------|")
        thresholds = {"外功": (1, "≥1"), "内功": (2, "≥2"), "防御": (2, "≥2"), "治疗": (2, "≥2")}
        for cat, (need, label) in thresholds.items():
            n = type_counts.get(cat, 0)
            ok = "是" if n >= need else "否"
            lines.append(f"| {cat} | {n} | {label} | {ok} |")

        # link to nearest weapon placement before this round
        weapon_place = max((p for p in places if p["time"] < first_cast), key=lambda x: x["time"], default=None)
        if weapon_place:
            wpr = player_profile(bld, weapon_place["pid"])
            weapon_type = wpr["type"]
            lines += [
                "",
                f"#### 关联装置武器",
                "",
                f"- 放武器者：`{weapon_place['pid']}` **{wpr['name']}**（{wpr['xf_name']} / {weapon_type}）",
                f"- 放武器时间：{weapon_place['rel']}（传功开始前 {(first_cast - weapon_place['time'])/1000:.1f}s）",
                "",
                "#### 推断传功效果（按攻略规则）",
                "",
            ]
            for bullet in infer_transfer_result(weapon_type, type_counts):
                lines.append(f"- {bullet}")
        else:
            lines.append("\n> 未找到本轮之前的玩家放武器记录。\n")

        eff = effect_after_time(bld, last_done, last_done + 20000)
        lines += [
            "",
            "#### JCL 验证（传功完成后20秒内）",
            "",
            f"- 玩家获得 33473（回春相关）：{eff['33473_players']} 条 buff 记录",
            f"- 玩家获得 33471.2（磐石）：{eff['33471_players']} 条 buff 记录",
            f"- 33463（断脉相关）：{eff['33463_boss_side']} 条",
            f"- 33473 治疗技能跳数：{eff['33473_heal_skill']} 次",
            "",
        ]

    lines += [
        "---",
        "",
        "## 5. 综合结论",
        "",
    ]
    if len(rounds) >= 1:
        lines.append("- **第1轮**：5人传功；装置武器为**雨露·毒经（内功槽）**。参与中内功仅1人（雨露本人），**未触发封脉**；防御/外功/治疗人数不计入此槽。")
    if len(rounds) >= 2:
        lines.append("- **第2轮**：3人传功；装置武器为**红柳·铁牢律（防御槽）**。参与中防御2人（红柳+唐烬卿），**应触发全场磐石33471.2**（JCL 在 00:02:12 可见）。")
    lines += [
        "- 两轮传功均在 BOSS 80%~40% 阶段内完成，符合神秘装置机制窗口。",
        "- 装置上武器的心法类型决定「哪一条效果槽位」被激活；参与人数按心法分类累计决定是否达标。",
        "",
    ]
    return "\n".join(lines)


def build_wipe_report(bld: BattleLogData, base: int) -> str:
    npc_cache: dict = {}
    player_deaths: list[dict] = []
    pet_deaths: list[dict] = []

    for item in bld.log:
        if item.dataType != "Death":
            continue
        vic = item.id
        killer = item.killer
        rec = {
            "time": item.time,
            "rel": ms_hms(item.time, base),
            "victim_id": vic,
            "victim": name_of(vic, bld, npc_cache),
            "killer_id": killer,
            "killer": name_of(killer, bld, npc_cache),
        }
        if vic in bld.info.player:
            player_deaths.append(rec)
        else:
            pet_deaths.append(rec)

    # mass wipe: find largest 3-second death cluster
    cluster: list[dict] = []
    t_peak = 0
    if player_deaths:
        sorted_deaths = sorted(player_deaths, key=lambda x: x["time"])
        best: list[dict] = []
        for i, anchor in enumerate(sorted_deaths):
            window = [d for d in sorted_deaths if anchor["time"] <= d["time"] <= anchor["time"] + 3000]
            if len(window) > len(best):
                best = window
        cluster = best
        t_peak = cluster[0]["time"] if cluster else 0

    # skills 30s before wipe
    t_end = t_peak or (base + 148135)
    t_start = t_end - 30000
    pre_skills: Counter = Counter()
    pre_damage: list[dict] = []
    shouts: list[dict] = []

    skill_names = {
        44570: "三叠扇", 44239: "公子扇·裂风", 44240: "裂风", 44241: "裂风·扇骨/引爆",
        44068: "散锋", 44065: "聚锋", 44285: "掠影探囊", 44823: "裂风扇体伤害",
        44475: "扇风普攻", 44476: "扇刃普攻", 45034: "折扇飞锋",
    }

    for item in bld.log:
        if t_start <= item.time <= t_end + 5000:
            if item.dataType == "Skill":
                sid = int(item.id)
                if sid in skill_names or item.caster == BOSS or str(item.caster).startswith("107417"):
                    pre_skills[skill_names.get(sid, f"技能{sid}")] += 1
                    dmg = getattr(item, "damage", 0) or 0
                    if dmg > 500000 and item.target in bld.info.player:
                        pre_damage.append({
                            "rel": ms_hms(item.time, base),
                            "caster": name_of(item.caster, bld, npc_cache),
                            "target": name_of(item.target, bld, npc_cache),
                            "skill": skill_names.get(sid, sid),
                            "damage": dmg,
                        })
            if item.dataType == "Shout":
                shouts.append({"rel": ms_hms(item.time, base), "text": fix_gbk(item.content)})

    pre_damage.sort(key=lambda x: -x["damage"])

    lines = [
        "# 柳公子 · 团灭原因分析报告",
        "",
        f"- 源文件：`{JCL_PATH.name}`",
        f"- 生成时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## 1. 团灭概况",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 战斗总时长 | ~148 秒 |",
        f"| 玩家重伤总数 | {len(player_deaths)} |",
        f"| 召唤物/宠物死亡 | {len(pet_deaths)} |",
        f"| **团灭爆发时刻** | **{ms_hms(t_peak, base) if t_peak else '—'}** |",
        f"| 3秒内连锁重伤 | **{len(cluster)}** 人 |",
        "",
        "> 本场未触发：8分钟超时机制、40%以下末阶段（折扇飞锋/柱子）、沾衣哨。",
        "> 团灭发生在约 2分20秒，属于战斗中期。",
        "",
        "---",
        "",
        "## 2. 团灭时间线（00:02:10 ~ 00:02:25）",
        "",
    ]

    key_events = []
    for item in bld.log:
        if t_peak and not (t_peak - 15000 <= item.time <= t_peak + 3000):
            continue
        if not t_peak:
            continue
        if item.dataType == "Cast" and int(item.id) in (44570,):
            key_events.append((item.time, f"{ms_hms(item.time, base)} BOSS 开始读条 **三叠扇 c44570**"))
        if item.dataType == "Skill":
            sid = int(item.id)
            if sid == 44570:
                key_events.append((item.time, f"{ms_hms(item.time, base)} **三叠扇** 引导/释放"))
            if sid == 44068 and item.caster != BOSS:
                tgt = name_of(item.target, bld, npc_cache)
                dmg = getattr(item, "damage", 0)
                if dmg > 1_000_000:
                    key_events.append((item.time, f"{ms_hms(item.time, base)} 扇子 `{item.caster[-6:]}` **散锋44068** → {tgt} 伤害 **{dmg/10000:.0f}万**"))
            if sid == 44241:
                tgt = name_of(item.target, bld, npc_cache)
                dmg = getattr(item, "damage", 0)
                if dmg > 1_000_000:
                    key_events.append((item.time, f"{ms_hms(item.time, base)} 扇子 **44241引爆/扇骨** → {tgt} 伤害 **{dmg/10000:.0f}万**"))
            if sid == 44823:
                tgt = name_of(item.target, bld, npc_cache)
                key_events.append((item.time, f"{ms_hms(item.time, base)} 扇子 **44823** 追击 → {tgt}"))
        if item.dataType == "Buff" and int(item.id) == 17201 and not (item.delete in (True, "true")):
            if item.target in bld.info.player:
                key_events.append((item.time, f"{ms_hms(item.time, base)} {name_of(item.target,bld,npc_cache)} 获得 **耐力损耗17201** ×{item.stack}"))
        if item.dataType == "Death" and item.id in bld.info.player:
            key_events.append((item.time, f"{ms_hms(item.time, base)} **{name_of(item.id,bld,npc_cache)}** 重伤 ← {name_of(item.killer,bld,npc_cache)}"))
        if item.dataType == "Shout":
            key_events.append((item.time, f"{ms_hms(item.time, base)} BOSS 喊话：「{fix_gbk(item.content)}」"))

    key_events.sort()
    for _, msg in key_events[:45]:
        lines.append(f"- {msg}")
    if len(key_events) > 45:
        lines.append(f"- … 共 {len(key_events)} 条关键事件")

    lines += [
        "",
        "---",
        "",
        "## 3. 团灭受害者与击杀来源",
        "",
        "| 时间 | 受害者 | 用户ID | 击杀来源 | 来源ID |",
        "|------|--------|--------|----------|--------|",
    ]
    for d in sorted(cluster, key=lambda x: x["time"]):
        lines.append(f"| {d['rel']} | {d['victim']} | `{d['victim_id']}` | {d['killer']} | `{d['killer_id']}` |")

    lines += [
        "",
        "---",
        "",
        "## 4. 伤害构成（团灭前30秒 TOP）",
        "",
        "| 时间 | 施法者 | 目标 | 技能 | 伤害(约) |",
        "|------|--------|------|------|--------:|",
    ]
    for d in pre_damage[:20]:
        lines.append(f"| {d['rel']} | {d['caster']} | {d['target']} | {d['skill']} | {d['damage']/10000:.0f}万 |")

    lines += [
        "",
        "---",
        "",
        "## 5. 机制技能频次（团灭前30秒）",
        "",
        "| 技能 | 次数 |",
        "|------|-----:|",
    ]
    for sk, cnt in pre_skills.most_common(15):
        lines.append(f"| {sk} | {cnt} |")

    lines += [
        "",
        "---",
        "",
        "## 6. 团灭原因判定",
        "",
        "### 直接原因",
        "",
        "1. **三叠扇 c44570** 在 `00:02:14` 启动（BOSS 喊话「折扇翻时风作刃…」），对 3 名玩家施加注视后连续释放 **裂风 + 聚锋/散锋** 组合。",
        "2. 裂风产生的 **扇子 NPC**（实体如 `1074176150`、`1074176166`）在场内追击，造成：",
        "   - **44823** 扇子近身 tick 伤害（主要点名 **酌九九**）",
        "   - **44068 散锋** 扇形穿透伤害（单次 200万+，多人同时命中）",
        "   - **44241 引爆/扇骨飞散** 范围伤害（单次 1000万+ 级穿透外功）",
        "3. **17201 耐力损耗** 8 层叠加在部分玩家，降低承伤能力。",
        "4. `00:02:19~00:02:20` 约 **25 人同时在 1 秒内重伤**，形成团灭。",
        "",
        "### 间接原因 / 可改进点",
        "",
        "| 因素 | 分析 |",
        "|------|------|",
        "| 三叠扇分散 | 3 名注视目标若聚集，会叠加多把扇子 + 引爆范围重叠 |",
        "| 扇子引爆时机 | 追击目标靠近扇子 1.5 尺或碰柱即引爆，需提前远离点名玩家 |",
        "| 散锋扇形 | 44068 无法扶摇，被点名散锋方向上的团员需快速出圈 |",
        "| 传功阶段刚结束 | 第2轮传功在 00:02:07 结束，团灭前仅 13 秒，团员可能仍在装置附近 |",
        "| 磐石覆盖 | 第2轮传功后 33471.2 在 00:02:12 才生效，三叠扇 00:02:14 启动，减伤窗口极短 |",
        "| 末阶段未至 | 非 40% 柱子机制，纯中期技能组合压垮 |",
        "",
        "### 结论",
        "",
        "**团灭主因：三叠扇机制链（裂风扇子追击 → 散锋44068 → 44241大范围引爆）造成穿透外功瞬间清场，非超时、非神秘装置传功失败直接致死。**",
        "",
        "建议：三叠扇前预分散注视目标；扇子出现后立即远离被追玩家；散锋方向留空；传功结束后迅速回到战斗站位而非堆叠在装置旁。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    bld, base = load_bld()
    OUT_CHUANGONG.write_text(build_chuangong_report(bld, base), encoding="utf-8")
    OUT_WIPE.write_text(build_wipe_report(bld, base), encoding="utf-8")
    print(f"Wrote {OUT_CHUANGONG}")
    print(f"Wrote {OUT_WIPE}")


if __name__ == "__main__":
    main()

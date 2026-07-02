#!/usr/bin/env python3
"""LGZ JCL parser v2: jx3bla base + Liu Gongzi mechanic rules."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

JX3BLA_ROOT = Path("/root/jx3bla")
sys.path.insert(0, str(JX3BLA_ROOT))

from data.DataContent import (  # noqa: E402
    SingleDataAlert,
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
OUT_V1 = JCL_PATH.with_suffix(".analysis.md")
OUT_V2 = JCL_PATH.with_suffix(".analysis.v2.md")
OUT_DIFF = JCL_PATH.with_suffix(".analysis.diff.md")
OUT_ERRORS = JCL_PATH.with_suffix(".parse_errors.v2.txt")

BOSS_ENTITY = "1074160857"

JX3BLA_KNOWN = {
    "1": "全局战斗信息", "2": "场景事件", "3": "场景事件", "4": "玩家信息", "5": "战斗状态",
    "6": "场景事件", "7": "场景事件", "8": "NPC信息", "9": "战斗状态", "12": "场景物件",
    "13": "Buff", "14": "喊话", "15": "系统预警", "19": "读条", "21": "技能", "28": "死亡/重伤",
}

V2_EXT_TYPES = {
    "10": "阶段标记(推测)",
    "11": "阶段标记(推测)",
    "18": "系统消息",
    "20": "实体坐标/移动采样(推测)",
    "23": "技能引导镜像",
    "25": "技能引导链接",
}

SKILLS = {
    44474: "普通攻击",
    44475: "扇风·普通攻击",
    44476: "扇刃·普通攻击",
    44239: "公子扇·裂风",
    44065: "聚锋",
    44066: "聚锋(释放)",
    44068: "散锋",
    44285: "掠影探囊",
    44570: "三叠扇",
    45010: "传功",
    45017: "破甲(外功传功结果)",
    45018: "封脉(内功传功结果)",
    44615: "沾衣哨",
    45034: "折扇飞锋(末阶段普攻)",
}

BUFFS = {
    32870: "注视(裂风/聚锋)",
    32993: "失财(掠影探囊)",
    33214: "注视(三叠扇)",
    33251: "沾衣哨",
    33300: "缴械(被BOSS夺走武器)",
    33506: "眩晕(缴械附带)",
    33563: "缴械(玩家主动放置武器)",
    33471: "磐石",
    33473: "回春",
    33463: "断脉",
    17201: "耐力损耗",
    33125: "伤口",
    33248: "震耳欲聋",
}

HEALER_XF = {10026, 10242, 10243, 10533, 10615, 10626, 10698, 10756, 10448}
TANK_XF = {10002, 10028, 10224, 10225, 10389, 10626}
DEF_XF = TANK_XF  # 防御心法


def fix_gbk(value: str) -> str:
    if not value or all(ord(c) < 128 for c in value):
        return value.strip('"')
    try:
        return value.encode("latin-1").decode("gbk").strip('"')
    except Exception:
        return value.strip('"')


def parse_filename(name: str) -> dict[str, str]:
    stem = name[4:] if name.upper().startswith("LGZ-") else name
    parts = stem.rsplit(".", 1)[0].split("-")
    if len(parts) >= 8:
        return {"datetime": "-".join(parts[:6]), "map": parts[6], "boss": parts[7]}
    return {"datetime": "?", "map": "?", "boss": "?"}


def ms_to_hms(ms: int, base: int | None) -> str:
    if base is not None:
        ms = max(0, ms - base)
    s = ms // 1000
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def xf_category(xf: str | int) -> str:
    try:
        x = int(xf)
    except Exception:
        return "未知"
    if x in HEALER_XF:
        return "治疗"
    if x in DEF_XF:
        return "防御"
    if x >= 10000:
        return "内功/外功(推测)"
    return "未知"


@dataclass
class ParseResult:
    bld: BattleLogData
    errors: list[str]
    type_counter: Counter
    ext_events: list[dict]
    encoding: str


def load_jcl(path: Path) -> ParseResult:
    raw = path.read_bytes()
    for enc in ("gbk", "utf-8", "latin-1"):
        try:
            content = raw.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    else:
        content = raw.decode("utf-8", errors="replace")
        encoding = "utf-8/replace"

    bld = BattleLogData(window=None)
    bld.dataType = "jcl"
    lta = LuaTableAnalyserToDict()
    errors: list[str] = []
    type_counter: Counter = Counter()
    ext_events: list[dict] = []
    first_info = True
    player_names: dict[str, str] = {}
    summon: dict[str, str] = {}

    for line_no, line in enumerate(content.strip("\n").split("\n"), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            errors.append(f"L{line_no}\t格式异常\t{line[:200]}")
            continue
        et = parts[4]
        type_counter[et] += 1
        try:
            parts[5] = lta.analyse(parts[5], delta=1)
        except Exception as exc:
            errors.append(f"L{line_no}\tLuaTable失败 type={et}\t{exc}\t{line[:240]}")
            continue

        t_ms = int(parts[3])
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
            elif et == "15":
                o = SingleDataAlert(); o.setByJcl(parts); bld.log.append(o)
            elif et == "1":
                if first_info:
                    bld.info.server = parts[5]["2"].split(":")[2].split("_")[1]
                    bld.info.battleTime = int(parts[5]["2"].split(":")[4])
                    first_info = False
                    bld.info.sumTime = 0
                else:
                    bld.info.sumTime = int(parts[5]["3"])
            elif et == "4":
                bld.info.addPlayer(parts[5]["1"], parts[5]["2"], parts[5]["3"])
                p = bld.info.player[parts[5]["1"]]
                p.xf = parts[5]["4"]
                p.equipScore = parts[5]["5"]
                if "6" in parts[5]:
                    p.equip = parts[5]["6"]
                if "7" in parts[5]:
                    p.qx = parts[5]["7"]
                player_names[fix_gbk(p.name)] = parts[5]["1"]
            elif et == "8":
                bld.info.addNPC(parts[5]["1"], parts[5]["2"])
                n = bld.info.npc[parts[5]["1"]]
                n.templateID = parts[5]["3"]
                n.x, n.y, n.z = int(parts[5]["5"]), int(parts[5]["6"]), int(parts[5]["7"])
                nm = fix_gbk(n.name)
                if "的" in nm:
                    cand = "的".join(nm.split("的")[:-1])
                    if cand in player_names:
                        summon[parts[5]["1"]] = player_names[cand]
                if parts[5]["4"] != "0":
                    summon[parts[5]["1"]] = parts[5]["4"]
            elif et == "12":
                bld.info.addDoodad(parts[5]["1"], parts[5]["2"])
                d = bld.info.doodad[parts[5]["1"]]
                d.x, d.y, d.z = int(parts[5]["3"]), int(parts[5]["4"]), int(parts[5]["5"])
            elif et in V2_EXT_TYPES:
                payload = parts[5]
                rec = {"line": line_no, "time": t_ms, "type": et, "raw": payload}
                if et == "20" and isinstance(payload, dict):
                    rec["entity"] = payload.get("1")
                    rec["value"] = payload.get("2")
                    rec["field3"] = payload.get("3")
                    rec["field4"] = payload.get("4")
                elif et == "23" and isinstance(payload, dict):
                    rec["entity"] = payload.get("1")
                    rec["skill_id"] = payload.get("4")
                elif et == "25" and isinstance(payload, dict):
                    rec["caster"] = payload.get("1")
                    rec["target"] = payload.get("2")
                    rec["skill_id"] = payload.get("4")
                    rec["level"] = payload.get("5")
                elif et == "18" and isinstance(payload, dict):
                    rec["content"] = fix_gbk(str(payload.get("1", "")))
                    rec["msg_type"] = payload.get("2")
                elif et in ("10", "11") and isinstance(payload, dict):
                    rec["marker"] = payload.get("1")
                ext_events.append(rec)
            else:
                errors.append(f"L{line_no}\t仍未识别 type={et}\t{line[:240]}")
        except Exception as exc:
            errors.append(f"L{line_no}\t结构化失败 type={et}\t{exc}\t{line[:200]}")

    meta = parse_filename(path.name)
    bld.info.map, bld.info.boss = meta["map"], meta["boss"]
    bld.info.skill = {}
    return ParseResult(bld, errors, type_counter, ext_events, encoding)


def name_of(eid: str, bld: BattleLogData) -> str:
    if eid in bld.info.player:
        return fix_gbk(bld.info.player[eid].name)
    if eid in bld.info.npc:
        return fix_gbk(bld.info.npc[eid].name)
    return eid


def analyze_lgz(bld: BattleLogData, ext_events: list[dict], base: int) -> dict:
    disarms: list[dict] = []
    placements: list[dict] = []
    transfers: list[dict] = []
    casts_45010: list[dict] = []
    mechanic_skills: list[dict] = []
    mechanic_buffs: list[dict] = []
    markers: list[dict] = []

    # buff-driven mechanics
    for item in bld.log:
        if item.dataType != "Buff":
            continue
        bid = int(item.id)
        if bid not in BUFFS:
            continue
        target = name_of(item.target, bld)
        caster = name_of(item.caster, bld)
        rec = {
            "time": item.time,
            "rel": ms_to_hms(item.time, base),
            "buff_id": bid,
            "buff": BUFFS[bid],
            "target": target,
            "caster": caster,
            "delete": item.delete in (True, "true"),
            "stack": item.stack,
        }
        mechanic_buffs.append(rec)
        if bid == 33300 and not rec["delete"]:
            disarms.append({**rec, "kind": "BOSS夺武"})
        if bid == 33563 and not rec["delete"]:
            placements.append({**rec, "kind": "玩家放置武器"})

    for item in bld.log:
        if item.dataType == "Cast":
            sid = int(item.id)
            if sid in SKILLS:
                casts_45010.append({
                    "time": item.time,
                    "rel": ms_to_hms(item.time, base),
                    "player": name_of(item.caster, bld),
                    "player_id": item.caster,
                    "skill_id": sid,
                    "skill": SKILLS.get(sid, str(sid)),
                    "via": "读条19",
                }) if sid == 45010 else mechanic_skills.append({
                    "time": item.time,
                    "rel": ms_to_hms(item.time, base),
                    "caster": name_of(item.caster, bld),
                    "skill_id": sid,
                    "skill": SKILLS.get(sid, str(sid)),
                    "via": "读条19",
                })
        elif item.dataType == "Skill":
            sid = int(item.id)
            if sid in SKILLS:
                rec = {
                    "time": item.time,
                    "rel": ms_to_hms(item.time, base),
                    "caster": name_of(item.caster, bld),
                    "target": name_of(item.target, bld),
                    "skill_id": sid,
                    "skill": SKILLS[sid],
                    "via": "技能21",
                }
                if sid == 45010:
                    casts_45010.append(rec)
                else:
                    mechanic_skills.append(rec)

    for ev in ext_events:
        if ev["type"] == "25":
            sid = int(ev.get("skill_id", 0) or 0)
            if sid in SKILLS:
                mechanic_skills.append({
                    "time": ev["time"],
                    "rel": ms_to_hms(ev["time"], base),
                    "caster": name_of(str(ev.get("caster")), bld),
                    "skill_id": sid,
                    "skill": SKILLS.get(sid, str(sid)),
                    "via": "引导25",
                })
        elif ev["type"] in ("10", "11"):
            markers.append(ev)

    # group 传功 rounds: 45010 cast clusters within 15s windows
    casts_45010.sort(key=lambda x: x["time"])
    rounds: list[dict] = []
    if casts_45010:
        cur = [casts_45010[0]]
        for c in casts_45010[1:]:
            if c["time"] - cur[-1]["time"] <= 15000:
                cur.append(c)
            else:
                rounds.append(cur)
                cur = [c]
        rounds.append(cur)

    for i, rnd in enumerate(rounds, 1):
        participants = {}
        for c in rnd:
            pid = c.get("player_id") or c.get("caster")
            pname = c.get("player") or c.get("caster")
            if pid not in participants:
                xf = bld.info.player[pid].xf if pid in bld.info.player else "?"
                participants[pid] = {
                    "name": pname,
                    "xf": xf,
                    "category": xf_category(xf),
                    "count": 0,
                }
            participants[pid]["count"] += 1
        transfers.append({
            "round": i,
            "start": ms_to_hms(rnd[0]["time"], base),
            "end": ms_to_hms(rnd[-1]["time"], base),
            "participants": list(participants.values()),
            "participant_count": len(participants),
        })

    return {
        "disarms": disarms,
        "placements": placements,
        "transfers": transfers,
        "casts_45010": casts_45010,
        "mechanic_skills": sorted(mechanic_skills, key=lambda x: x["time"]),
        "mechanic_buffs": mechanic_buffs,
        "markers": markers,
        "ext_type20_count": sum(1 for e in ext_events if e["type"] == "20"),
    }


def build_v2_md(res: ParseResult, lgz: dict) -> str:
    bld = res.bld
    base = min((x.time for x in bld.log), default=0)
    meta = parse_filename(JCL_PATH.name)
    lines: list[str] = []

    lines += [
        "# JCL 解析分析报告 v2（jx3bla + 柳公子机制规则）",
        "",
        f"- 源文件：`{JCL_PATH}`",
        f"- 解析引擎：jx3bla + LGZ 机制 ID 规则",
        f"- 生成时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- 文件编码：{res.encoding}",
        "",
        "## 1. 文件元信息",
        "",
        "| 字段 | 值 |",
        "|------|-----|",
        f"| 战斗时间 | {meta['datetime']} |",
        f"| 副本 | {meta['map']} |",
        f"| 首领 | {meta['boss']} |",
        f"| BOSS实体ID | {BOSS_ENTITY} |",
        f"| 服务器 | {bld.info.server} |",
        f"| 记录时长 | {bld.info.sumTime} ms ({bld.info.sumTime/1000:.1f}s) |",
        f"| 结构化事件 | {len(bld.log)} |",
        f"| 扩展解析事件 | {len(res.ext_events)} |",
        f"| 仍失败行 | {len(res.errors)} |",
        "",
    ]

    lines += ["## 2. 事件类型统计（含 v2 扩展）", "", "| 类型 | 含义 | 数量 |", "|------|------|-----:|"]
    for et, cnt in res.type_counter.most_common():
        meaning = JX3BLA_KNOWN.get(et) or V2_EXT_TYPES.get(et, "仍未识别")
        lines.append(f"| `{et}` | {meaning} | {cnt} |")
    lines.append("")

    lines += ["## 3. 柳公子机制时间轴", ""]

    lines += ["### 3.1 神秘装置 · 缴械/放置武器", ""]
    if lgz["disarms"]:
        lines += ["**BOSS 夺武（debuff 33300）**", "", "| 时间 | 目标 | 心法类型 |", "|------|------|----------|"]
        for d in lgz["disarms"]:
            pid = d["target"]
            xf = bld.info.player.get(next((k for k,v in bld.info.player.items() if fix_gbk(v.name)==pid), ""), None)
            cat = xf_category(getattr(xf, "xf", "?")) if xf else "?"
            lines.append(f"| {d['rel']} | {d['target']} | {cat} |")
    else:
        lines.append("未检测到 33300 缴械。")
    lines.append("")
    if lgz["placements"]:
        lines += ["**玩家放置武器（debuff 33563）**", "", "| 时间 | 玩家 |", "|------|------|"]
        for p in lgz["placements"]:
            lines.append(f"| {p['rel']} | {p['target']} |")
    else:
        lines.append("未检测到 33563 玩家放置武器。")
    lines.append("")

    lines += ["### 3.2 传功 c45010", ""]
    if lgz["transfers"]:
        for tr in lgz["transfers"]:
            lines.append(f"#### 第 {tr['round']} 轮 ({tr['start']} ~ {tr['end']})")
            lines.append("")
            lines.append(f"- 参与人数：**{tr['participant_count']}**")
            lines.append("")
            lines.append("| 玩家 | 心法ID | 类型 | 传功动作次数 |")
            lines.append("|------|--------|------|-------------:|")
            for p in tr["participants"]:
                lines.append(f"| {p['name']} | {p['xf']} | {p['category']} | {p['count']} |")
            lines.append("")
            # infer expected effect per guide
            cats = {p["category"] for p in tr["participants"]}
            n = tr["participant_count"]
            effect = []
            if n >= 1 and "内功/外功(推测)" in cats:
                effect.append("外功1人→破甲s45017 / 内功2人→封脉s45018(需2人)")
            if n >= 2 and "防御" in cats:
                effect.append("防御2人→全场磐石33471.2")
            if n >= 2 and "治疗" in cats:
                effect.append("治疗2人→全场回春33473.2")
            if effect:
                lines.append("机制对照（按攻略）：")
                for e in effect:
                    lines.append(f"- {e}")
            lines.append("")
    else:
        lines.append("未检测到 45010 传功读条/技能。")
    lines.append("")

    lines += ["### 3.3 关键技能时间线（攻略 ID）", ""]
    if lgz["mechanic_skills"]:
        lines.append("| 时间 | 施法者 | 目标 | 技能 | 来源 |")
        lines.append("|------|--------|------|------|------|")
        for s in lgz["mechanic_skills"][:60]:
            lines.append(f"| {s['rel']} | {s.get('caster','?')} | {s.get('target','-')} | {s['skill']}({s['skill_id']}) | {s['via']} |")
        if len(lgz["mechanic_skills"]) > 60:
            lines.append(f"\n> 共 {len(lgz['mechanic_skills'])} 条，仅展示前 60。")
    else:
        lines.append("无匹配技能。")
    lines.append("")

    lines += ["### 3.4 关键 Buff/debuff", ""]
    applied = [b for b in lgz["mechanic_buffs"] if not b["delete"]]
    removed = [b for b in lgz["mechanic_buffs"] if b["delete"]]
    lines.append(f"- 施加记录：{len(applied)} 条；移除记录：{len(removed)} 条")
    lines.append("")
    focus = Counter(b["buff"] for b in applied)
    lines.append("| Buff | 施加次数 |")
    lines.append("|------|--------:|")
    for name, cnt in focus.most_common():
        lines.append(f"| {name} | {cnt} |")
    lines.append("")

    lines += ["## 4. 扩展事件 type=20（坐标采样，原样保留字段）", ""]
    lines.append(f"共 **{lgz['ext_type20_count']}** 条。示例：")
    lines.append("")
    lines.append("```text")
    samples = [e for e in res.ext_events if e["type"] == "20"][:8]
    for s in samples:
        lines.append(
            f"L{s['line']} t={s['time']} entity={s.get('entity')} value={s.get('value')} f3={s.get('field3')} f4={s.get('field4')}"
        )
    lines.append("```")
    lines.append("")
    lines.append("> 攻略未给出 type=20 语义；当前按「实体坐标/移动采样」归档，不做机制推断。")
    lines.append("")

    lines += ["## 5. 仍未解析行", ""]
    if res.errors:
        lines.append(f"共 {len(res.errors)} 条，详见 `{OUT_ERRORS.name}`")
        lines.append("")
        lines.append("```text")
        for row in res.errors[:40]:
            lines.append(row)
        if len(res.errors) > 40:
            lines.append(f"... 其余 {len(res.errors)-40} 条")
        lines.append("```")
    else:
        lines.append("全部行均已结构化。")
    lines.append("")

    lines += ["## 6. 结论", ""]
    lines.append("- v2 在 jx3bla 基础上新增了 10/11/18/20/23/25 事件解析。")
    lines.append("- 已按攻略 ID 提取：缴械、放置武器、传功轮次、三叠扇/掠影探囊/聚锋散锋等。")
    lines.append("- 传功「效果判定」(破甲/封脉/磐石/回春) 需结合参与人数+心法类型+后续 buff 33471/33473/33463 二次验证。")
    lines.append("- type=20 仍无官方语义，仅保留原始字段。")
    lines.append("")
    return "\n".join(lines)


def build_diff(v1_stats: dict, v2_stats: dict, lgz: dict) -> str:
    lines = [
        "# JCL 解析 v1 vs v2 差异对比",
        "",
        f"- v1 报告：`{OUT_V1.name}`",
        f"- v2 报告：`{OUT_V2.name}`",
        "",
        "## 1. 解析覆盖率",
        "",
        "| 指标 | v1 (jx3bla) | v2 (+LGZ规则) | 差异 |",
        "|------|------------:|-------------:|------|",
    ]
    for key, label in [
        ("structured", "结构化事件数"),
        ("errors", "失败/保留行"),
        ("players", "识别玩家数"),
    ]:
        a, b = v1_stats.get(key, 0), v2_stats.get(key, 0)
        diff = b - a
        sign = f"+{diff}" if diff > 0 else str(diff)
        lines.append(f"| {label} | {a} | {b} | {sign} |")
    lines.append("")
    lines += [
        "## 2. 新增能力（v2 独有）",
        "",
        "| 能力 | v1 | v2 |",
        "|------|----|----|",
        "| 扩展事件 10/11/18/20/23/25 | 全部记入失败 | 结构化解析 |",
        f"| 传功 c45010 轮次 | 无 | **{len(lgz['transfers'])}** 轮 |",
        f"| BOSS夺武 33300 | 无 | **{len(lgz['disarms'])}** 次 |",
        f"| 玩家放武器 33563 | 无 | **{len(lgz['placements'])}** 次 |",
        f"| 机制技能追踪 | 无 | **{len(lgz['mechanic_skills'])}** 条 |",
        f"| 机制 buff 追踪 | 无 | **{len(lgz['mechanic_buffs'])}** 条 |",
        "",
        "## 3. 仍无法实现（相对 Inkar LGZAnalyze）",
        "",
        "- 自动推断「缴械→放武器→传功→取回武器」完整链路并分组",
        "- 精确识别每次传功是否触发破甲/封脉/磐石/回春（需二次关联后续技能/buff）",
        "- 扇子裂风力量层数、扇骨飞散、柱子高度联动",
        "- 8 分钟超时全员重伤的精确触发点标注",
        "",
        "## 4. 关键发现",
        "",
    ]
    if lgz["transfers"]:
        lines.append(f"- 本场检测到 **{len(lgz['transfers'])}** 轮传功，参与人数分别为："
                      + "、".join(str(t['participant_count']) for t in lgz['transfers']))
    if lgz["disarms"]:
        lines.append(f"- BOSS 夺武事件 **{len(lgz['disarms'])}** 次，与神秘装置机制吻合。")
    lines.append(f"- type=20 事件 **{lgz['ext_type20_count']}** 条已保留字段，语义仍未知。")
    lines.append("")
    return "\n".join(lines)


def read_v1_stats() -> dict:
    # from prior run constants embedded in v1 md
    return {"structured": 148033, "errors": 5748, "players": 25}


def main() -> None:
    res = load_jcl(JCL_PATH)
    base = min((x.time for x in res.bld.log), default=0)
    lgz = analyze_lgz(res.bld, res.ext_events, base)
    OUT_V2.write_text(build_v2_md(res, lgz), encoding="utf-8")
    OUT_ERRORS.write_text("\n".join(res.errors), encoding="utf-8")

    v2_stats = {
        "structured": len(res.bld.log) + len(res.ext_events),
        "errors": len(res.errors),
        "players": len(res.bld.info.player),
    }
    OUT_DIFF.write_text(build_diff(read_v1_stats(), v2_stats, lgz), encoding="utf-8")
    print(json.dumps({"v2_stats": v2_stats, "lgz_rounds": len(lgz["transfers"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()

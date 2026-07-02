#!/usr/bin/env python3
"""Parse JCL using jx3bla logic and emit analysis markdown."""

from __future__ import annotations

import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

JX3BLA_ROOT = Path("/root/jx3bla")
sys.path.insert(0, str(JX3BLA_ROOT))

from data.BattleLogData import BattleLogData  # noqa: E402
from tools.LoadData import LuaTableAnalyserToDict  # noqa: E402


JCL_PATH = Path(
    "/root/Inkar-Suki/testdata/"
    "LGZ-2026-05-13-22-41-46-25人英雄阆风悬城(795)-柳公子(137135).jcl"
)
OUT_PATH = JCL_PATH.with_suffix(".analysis.md")
RAW_ERROR_PATH = JCL_PATH.with_suffix(".parse_errors.txt")

# jx3bla known event type mapping (BattleLogData.loadFromJcl)
KNOWN_EVENT_TYPES = {
    "1": "全局战斗信息",
    "2": "场景事件",
    "3": "场景事件",
    "4": "玩家信息",
    "5": "战斗状态(进战/脱战)",
    "6": "场景事件",
    "7": "场景事件",
    "8": "NPC信息",
    "9": "战斗状态(进战/脱战)",
    "12": "场景物件",
    "13": "Buff",
    "14": "喊话",
    "15": "系统预警",
    "19": "读条",
    "21": "技能",
    "28": "死亡/重伤",
}


def fix_gbk_text(value: str) -> str:
    if not value:
        return value
    if all(ord(ch) < 128 for ch in value):
        return value
    try:
        return value.encode("latin-1").decode("gbk")
    except Exception:
        return value


def parse_filename_meta(name: str) -> dict[str, str]:
    stem = name
    if stem.upper().startswith("LGZ-"):
        stem = stem[4:]
    parts = stem.rsplit(".", 1)[0].split("-")
    if len(parts) >= 8:
        return {
            "datetime": "-".join(parts[0:6]),
            "map": parts[6],
            "boss": parts[7],
        }
    return {"datetime": "未知", "map": "未知", "boss": "未知"}


def ms_to_hms(ms: int, base_ms: int | None = None) -> str:
    if base_ms is not None:
        ms = max(0, ms - base_ms)
    sec = ms // 1000
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def load_with_error_capture(file_path: Path) -> tuple[BattleLogData, list[str], Counter, Counter]:
    errors: list[str] = []
    type_counter: Counter = Counter()
    unknown_type_counter: Counter = Counter()

    bld = BattleLogData(window=None)
    bld.dataType = "jcl"
    lta_dict = LuaTableAnalyserToDict()
    first_battle_info = True

    raw_text = file_path.read_bytes()
    for encoding in ("gbk", "utf-8", "latin-1"):
        try:
            content = raw_text.decode(encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue
    else:
        content = raw_text.decode("utf-8", errors="replace")
        used_encoding = "utf-8/replace"

    lines = content.strip("\n").split("\n")
    player_name_dict: dict[str, str] = {}
    summon_dict: dict[str, str] = {}

    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            errors.append(f"L{line_no}\t格式异常(列数={len(parts)})\t{line[:200]}")
            continue

        event_type = parts[4]
        type_counter[event_type] += 1

        try:
            parts[5] = lta_dict.analyse(parts[5], delta=1)
        except Exception as exc:
            errors.append(f"L{line_no}\tLuaTable解析失败 type={event_type}\t{exc}\t{line[:240]}")
            continue

        try:
            if event_type == "13":
                from data.DataContent import SingleDataBuff

                single = SingleDataBuff()
            elif event_type == "21":
                from data.DataContent import SingleDataSkill

                single = SingleDataSkill()
                if parts[5]["1"] in summon_dict:
                    parts[5]["1"] = summon_dict[parts[5]["1"]]
            elif event_type == "28":
                from data.DataContent import SingleDataDeath

                single = SingleDataDeath()
            elif event_type == "14":
                from data.DataContent import SingleDataShout

                single = SingleDataShout()
            elif event_type in ("5", "9"):
                from data.DataContent import SingleDataBattle

                single = SingleDataBattle()
            elif event_type in ("2", "3", "6", "7"):
                from data.DataContent import SingleDataScene

                single = SingleDataScene()
            elif event_type == "19":
                from data.DataContent import SingleDataCast

                single = SingleDataCast()
            elif event_type == "15":
                from data.DataContent import SingleDataAlert

                single = SingleDataAlert()
            elif event_type == "1":
                if first_battle_info:
                    bld.info.server = parts[5]["2"].split(":")[2].split("_")[1]
                    bld.info.battleTime = int(parts[5]["2"].split(":")[4])
                    first_battle_info = False
                    bld.info.sumTime = 0
                else:
                    bld.info.sumTime = int(parts[5]["3"])
                continue
            elif event_type == "4":
                bld.info.addPlayer(parts[5]["1"], parts[5]["2"], parts[5]["3"])
                player = bld.info.player[parts[5]["1"]]
                player.xf = parts[5]["4"]
                player.equipScore = parts[5]["5"]
                if "6" in parts[5]:
                    player.equip = parts[5]["6"]
                if "7" in parts[5]:
                    player.qx = parts[5]["7"]
                player_name_dict[fix_gbk_text(player.name)] = parts[5]["1"]
                continue
            elif event_type == "8":
                bld.info.addNPC(parts[5]["1"], parts[5]["2"])
                npc = bld.info.npc[parts[5]["1"]]
                npc.templateID = parts[5]["3"]
                npc.x = int(parts[5]["5"])
                npc.y = int(parts[5]["6"])
                npc.z = int(parts[5]["7"])
                npc_name = fix_gbk_text(npc.name)
                if "的" in npc_name:
                    possible = "的".join(npc_name.strip('"').split("的")[:-1])
                    if possible in player_name_dict:
                        summon_dict[parts[5]["1"]] = player_name_dict[possible]
                if parts[5]["4"] != "0":
                    summon_dict[parts[5]["1"]] = parts[5]["4"]
                continue
            elif event_type == "12":
                bld.info.addDoodad(parts[5]["1"], parts[5]["2"])
                bld.info.doodad[parts[5]["1"]].x = int(parts[5]["3"])
                bld.info.doodad[parts[5]["1"]].y = int(parts[5]["4"])
                bld.info.doodad[parts[5]["1"]].z = int(parts[5]["5"])
                continue
            else:
                unknown_type_counter[event_type] += 1
                errors.append(f"L{line_no}\t未识别事件类型={event_type}\t{line[:240]}")
                continue

            single.setByJcl(parts)
            bld.log.append(single)
        except Exception as exc:
            errors.append(
                f"L{line_no}\t事件结构化失败 type={event_type}\t{exc}\t{traceback.format_exc(limit=1).strip()}"
            )

    meta = parse_filename_meta(file_path.name)
    bld.info.skill = {}
    bld.info.map = meta["map"]
    bld.info.boss = meta["boss"]

    bld._parse_encoding = used_encoding  # type: ignore[attr-defined]
    return bld, errors, type_counter, unknown_type_counter


def resolve_name(entity_id: str, bld: BattleLogData) -> str:
    if entity_id in bld.info.player:
        return fix_gbk_text(bld.info.player[entity_id].name)
    if entity_id in bld.info.npc:
        return fix_gbk_text(bld.info.npc[entity_id].name)
    return entity_id


def build_markdown(
    bld: BattleLogData,
    errors: list[str],
    type_counter: Counter,
    unknown_type_counter: Counter,
    file_path: Path,
) -> str:
    meta = parse_filename_meta(file_path.name)
    event_times = [item.time for item in bld.log if hasattr(item, "time")]
    base_time = min(event_times) if event_times else None

    damage_by_player: dict[str, int] = defaultdict(int)
    heal_by_player: dict[str, int] = defaultdict(int)
    deaths: list[tuple[int, str, str]] = []
    shouts: list[tuple[int, str, str]] = []
    casts: list[tuple[int, str, str]] = []
    battle_events: list[tuple[int, str, str, int]] = []

    for item in bld.log:
        if item.dataType == "Skill":
            if item.damageEff > 0:
                damage_by_player[item.caster] += item.damageEff
            if item.healEff > 0:
                heal_by_player[item.caster] += item.healEff
        elif item.dataType == "Death":
            deaths.append((item.time, resolve_name(item.id, bld), resolve_name(item.killer, bld)))
        elif item.dataType == "Shout":
            shouts.append((item.time, fix_gbk_text(item.name), fix_gbk_text(item.content)))
        elif item.dataType == "Cast":
            casts.append((item.time, resolve_name(item.caster, bld), str(item.id)))
        elif item.dataType == "Battle":
            battle_events.append((item.time, resolve_name(item.id, bld), "进战" if item.fight else "脱战", item.hp))

    lines: list[str] = []
    lines.append("# JCL 解析分析报告")
    lines.append("")
    lines.append(f"- 源文件：`{file_path}`")
    lines.append(f"- 解析引擎：[jx3bla](https://github.com/moeheart/jx3bla) `BattleLogData.loadFromJcl` 逻辑")
    lines.append(f"- 生成时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append(f"- 文件编码：{getattr(bld, '_parse_encoding', 'unknown')}")
    lines.append("")

    lines.append("## 1. 文件元信息")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 战斗时间 | {meta['datetime']} |")
    lines.append(f"| 副本 | {meta['map']} |")
    lines.append(f"| 首领 | {meta['boss']} |")
    lines.append(f"| 服务器标识 | {bld.info.server or '未解析'} |")
    lines.append(f"| 战斗开始时间戳 | {bld.info.battleTime or '未解析'} |")
    lines.append(
        f"| 事件时间基准 | {base_time} ms（取结构化事件最早时间戳） |"
        if base_time is not None
        else "| 事件时间基准 | 未解析 |"
    )
    lines.append(
        f"| 记录战斗时长 | {bld.info.sumTime} ms ({bld.info.sumTime / 1000:.1f}s)"
        if bld.info.sumTime
        else "| 记录战斗时长 | 未解析 |"
    )
    lines.append(f"| 事件总行数 | {sum(type_counter.values())} |")
    lines.append(f"| 结构化成功事件 | {len(bld.log)} |")
    lines.append(f"| 解析失败/保留行 | {len(errors)} |")
    lines.append("")

    lines.append("## 2. 事件类型统计")
    lines.append("")
    lines.append("| 类型码 | jx3bla 含义 | 数量 |")
    lines.append("|--------|-------------|------:|")
    for event_type, count in sorted(type_counter.items(), key=lambda x: (-x[1], x[0])):
        meaning = KNOWN_EVENT_TYPES.get(event_type, "**未在 jx3bla 映射**")
        lines.append(f"| `{event_type}` | {meaning} | {count} |")
    lines.append("")

    if unknown_type_counter:
        lines.append("### 2.1 未能映射的事件类型（原样保留）")
        lines.append("")
        for event_type, count in unknown_type_counter.most_common():
            lines.append(f"- 类型 `{event_type}`：{count} 条")
        lines.append("")

    lines.append("## 3. 团队玩家")
    lines.append("")
    if not bld.info.player:
        lines.append("未解析到玩家信息。")
    else:
        lines.append("| 角色名 | 门派代码 | 心法ID | 装分 | 全局ID |")
        lines.append("|--------|----------|--------|-----:|--------|")
        for pid, player in sorted(
            bld.info.player.items(), key=lambda x: -(int(x[1].equipScore) if str(x[1].equipScore).isdigit() else 0)
        ):
            lines.append(
                f"| {fix_gbk_text(player.name)} | {player.occ} | {player.xf} | {player.equipScore} | {pid} |"
            )
    lines.append("")

    lines.append("## 4. 通用战斗统计（jx3bla 可解析部分）")
    lines.append("")
    lines.append("### 4.1 有效伤害 Top 15")
    lines.append("")
    if damage_by_player:
        lines.append("| 排名 | 角色 | 有效伤害 |")
        lines.append("|-----:|------|--------:|")
        for idx, (pid, dmg) in enumerate(sorted(damage_by_player.items(), key=lambda x: -x[1])[:15], 1):
            lines.append(f"| {idx} | {resolve_name(pid, bld)} | {dmg:,} |")
    else:
        lines.append("无有效伤害事件。")
    lines.append("")

    lines.append("### 4.2 有效治疗 Top 15")
    lines.append("")
    if heal_by_player:
        lines.append("| 排名 | 角色 | 有效治疗 |")
        lines.append("|-----:|------|--------:|")
        for idx, (pid, heal) in enumerate(sorted(heal_by_player.items(), key=lambda x: -x[1])[:15], 1):
            lines.append(f"| {idx} | {resolve_name(pid, bld)} | {heal:,} |")
    else:
        lines.append("无有效治疗事件。")
    lines.append("")

    lines.append("### 4.3 死亡/重伤记录")
    lines.append("")
    if deaths:
        lines.append("| 相对时间 | 受害者 | 来源 |")
        lines.append("|----------|--------|------|")
        for t, victim, killer in deaths[:50]:
            lines.append(f"| {ms_to_hms(t, base_time)} | {victim} | {killer} |")
        if len(deaths) > 50:
            lines.append(f"\n> 共 {len(deaths)} 条，仅展示前 50 条。")
    else:
        lines.append("无死亡/重伤事件。")
    lines.append("")

    lines.append("### 4.4 BOSS/系统喊话（前 30 条）")
    lines.append("")
    if shouts:
        lines.append("| 相对时间 | 喊话者 | 内容 |")
        lines.append("|----------|--------|------|")
        for t, name, content in shouts[:30]:
            content = content.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {ms_to_hms(t, base_time)} | {name} | {content} |")
        if len(shouts) > 30:
            lines.append(f"\n> 共 {len(shouts)} 条，仅展示前 30 条。")
    else:
        lines.append("无喊话事件。")
    lines.append("")

    lines.append("### 4.5 进战/脱战事件（前 30 条）")
    lines.append("")
    if battle_events:
        lines.append("| 相对时间 | 对象 | 状态 | 当前气血 |")
        lines.append("|----------|------|------|--------:|")
        for t, name, state, hp in battle_events[:30]:
            lines.append(f"| {ms_to_hms(t, base_time)} | {name} | {state} | {hp:,} |")
    else:
        lines.append("无进战/脱战事件。")
    lines.append("")

    lines.append("## 5. 柳公子 LGZ 专项分析")
    lines.append("")
    lines.append(
        "Inkar-Suki 的 `LGZAnalyze` 需要闭源 `cqc_url/lgz_analyze` 才能输出「点名缴械 / 放置武器 / 传功完成」时间轴。"
    )
    lines.append("jx3bla 仓库中也**没有**柳公子专项模块，因此本节只能标注当前无法自动推断的专项字段：")
    lines.append("")
    lines.append("| 专项字段 | 状态 | 说明 |")
    lines.append("|----------|------|------|")
    lines.append("| `disarm_name / disarm_time` | 未实现 | 需柳公子机制规则 + Buff/技能 ID 映射 |")
    lines.append("| `placer_name / placer_time` | 未实现 | 需识别「放置武器」事件 |")
    lines.append("| `transferer_name / transferer_time` | 未实现 | 需识别传功链路 |")
    lines.append("| 传功轮次分组 | 未实现 | Inkar 按轮次 flush 表格 |")
    lines.append("")
    lines.append(
        "> 本报告保留了全部原始可解析事件；如需 LGZ 专项结论，需要在 jx3bla 通用事件流之上追加 BOSS 规则。"
    )
    lines.append("")

    lines.append("## 6. 解析失败 / 未结构化保留项")
    lines.append("")
    if errors:
        lines.append(f"共 **{len(errors)}** 条。完整原文见：`{RAW_ERROR_PATH.name}`")
        lines.append("")
        lines.append("```text")
        for row in errors[:80]:
            lines.append(row)
        if len(errors) > 80:
            lines.append(f"... 其余 {len(errors) - 80} 条见 {RAW_ERROR_PATH.name}")
        lines.append("```")
    else:
        lines.append("全部行均已按 jx3bla 已知规则结构化，无失败行。")
    lines.append("")

    lines.append("## 7. 结论")
    lines.append("")
    lines.append("- **底层 JCL 解析成功**：事件流、玩家、伤害/治疗、死亡、喊话等通用字段可读取。")
    lines.append("- **LGZ 专项机制未解析**：柳公子传功分析不在 jx3bla 能力范围内。")
    lines.append("- **建议下一步**：基于 Buff/喊话/读条事件，对照游戏内机制 ID 手工补充 LGZ 规则。")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    bld, errors, type_counter, unknown_type_counter = load_with_error_capture(JCL_PATH)
    markdown = build_markdown(bld, errors, type_counter, unknown_type_counter, JCL_PATH)
    OUT_PATH.write_text(markdown, encoding="utf-8")
    RAW_ERROR_PATH.write_text("\n".join(errors), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {RAW_ERROR_PATH}")
    print(f"structured={len(bld.log)} errors={len(errors)} players={len(bld.info.player)}")


if __name__ == "__main__":
    main()

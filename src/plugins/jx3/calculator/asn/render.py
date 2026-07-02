"""阿史那承庆分析结果渲染."""

from __future__ import annotations

from jinja2 import Template
from nonebot.adapters.onebot.v11 import MessageSegment as ms

from src.const.jx3.kungfu import Kungfu
from src.const.path import ASSETS, TEMPLATES
from src.templates import get_saohua
from src.utils.file import read
from src.utils.generate import generate

from .._template import (
    asn_qte_table,
    asn_qte_template_body_main,
    hps_detail_template_body_main,
    hps_detail_template_body_sub,
    yxc_table,
)
from ..lgz.parser import skill_display_name
from .compute import AsnAnalysisResult


async def render_asn_images(
    data: AsnAnalysisResult,
    anonymous: bool = False,
) -> list[ms]:
    qte_tables: list[str] = []
    for wave in data.jiqu_waves:
        rows = []
        for rank, entry in enumerate(wave.qte_po, 1):
            name = "匿名玩家" if anonymous else entry.name
            rows.append(
                Template(asn_qte_template_body_main).render(
                    name=f"#{rank} {name}",
                    good=entry.value,
                    bad=int(entry.extra.get("bad", 0)),
                )
            )
        if not rows:
            rows.append(
                Template(asn_qte_template_body_main).render(
                    name="（本轮无 QTE 破记录）",
                    good=0,
                    bad=0,
                )
            )
        title_row = (
            f'<tr class="main-row"><td colspan="3" style="text-align:center;font-weight:bold;">'
            f"第{wave.index}波汲取 @{wave.start_rel}</td></tr>"
        )
        qte_tables.append(
            Template(yxc_table).render(
                tables=title_row + "\n" + Template(asn_qte_table).render(tables="\n".join(rows))
            )
        )

    qte_html = Template(read(TEMPLATES + "/jx3/health_detail.html")).render(
        font=ASSETS + "/font/PingFangSC-Semibold.otf",
        tables="\n".join(qte_tables) if qte_tables else "",
        saohua=get_saohua(),
        function_name="阿史那承庆 · 汲取 QTE（破）排名",
    )
    qte_image = await generate(qte_html, ".container", segment=True)

    heal_sections: list[str] = []
    for rnd in data.dead_rounds:
        tables: list[str] = []
        total = sum(e.value for e in rnd.shield_heal) or 1
        for rank, entry in enumerate(rnd.shield_heal, 1):
            name = "匿名玩家" if anonymous else entry.name
            tables.append(
                Template(hps_detail_template_body_main).render(
                    icon=Kungfu.with_internel_id(entry.xf_id, True).icon,
                    name=f"#{rank} {name}",
                    value=entry.value,
                )
            )
            skills_raw: dict[int, list[int]] = entry.extra.get("skills", {})
            skills = sorted(skills_raw.items(), key=lambda item: sum(item[1]), reverse=True)
            for skill_id, skill_values in skills:
                skill_total = sum(skill_values)
                tables.append(
                    Template(hps_detail_template_body_sub).render(
                        name=skill_display_name(int(skill_id)),
                        count=len(skill_values),
                        value=skill_total,
                        percent=f"{round(skill_total / entry.value * 100, 2) if entry.value else 0}%",
                    )
                )
            if not skills:
                tables.append(
                    Template(hps_detail_template_body_sub).render(
                        name="（无技能明细）",
                        count=0,
                        value=0,
                        percent="0%",
                    )
                )
        if not tables:
            tables.append(
                Template(hps_detail_template_body_main).render(
                    icon="",
                    name="（本轮无索命期间治疗记录）",
                    value=0,
                )
            )
        title = (
            f'<p style="text-align:center;font-weight:bold;margin:12px 0;">'
            f"第{rnd.index}轮死侍 @{rnd.start_rel} · 约{rnd.servant_count}人</p>"
        )
        heal_sections.append(title + Template(yxc_table).render(tables="\n".join(tables)))

    heal_html = Template(read(TEMPLATES + "/jx3/health_detail.html")).render(
        font=ASSETS + "/font/PingFangSC-Semibold.otf",
        tables="\n".join(heal_sections) if heal_sections else "",
        saohua=get_saohua(),
        function_name="阿史那承庆 · 死侍索命期间治疗排名",
    )
    heal_image = await generate(heal_html, ".container", segment=True)

    return [qte_image, heal_image]

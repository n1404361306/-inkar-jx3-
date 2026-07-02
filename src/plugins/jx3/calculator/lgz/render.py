"""渲染柳公子分析报告（Pillow 轻量绘图，避免 Playwright OOM）."""

from __future__ import annotations

import gc
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from nonebot.adapters.onebot.v11 import MessageSegment as ms

from src.const.path import ASSETS, CACHE, build_path
from src.utils.generate import get_uuid

from .parser import LGZAnalysisResult, TransferRound, check_memory_available

WIDTH = 1400
PAD = 28
LINE = 34
LINE_SM = 28
GROW_STEP = 512
FONT_PATH = build_path(ASSETS, ["font", "PingFangSC-Semibold.otf"])

# 事件类型 → (文字色, 行背景色)
EVENT_STYLE: dict[str, tuple[str, str]] = {
    "缴械点名": ("#C45C00", "#FFF4E8"),
    "缴械": ("#C45C00", "#FFF4E8"),
    "放置武器": ("#6B3FA0", "#F3EDFF"),
    "放武器": ("#6B3FA0", "#F3EDFF"),
    "传功开始": ("#1A6FB5", "#EBF5FF"),
    "传功完成": ("#1A6FB5", "#EBF5FF"),
    "传功": ("#1A6FB5", "#EBF5FF"),
    "传功生效": ("#1B7A3D", "#E8F8EE"),
    "传功中断": ("#B91C1C", "#FDECEC"),
}

LEGEND_ITEMS = (
    ("缴械", "#C45C00"),
    ("放武器", "#6B3FA0"),
    ("传功", "#1A6FB5"),
    ("传功生效", "#1B7A3D"),
    ("传功中断", "#B91C1C"),
)

_FONT_CACHE: tuple[ImageFont.FreeTypeFont, ...] | None = None


def _fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    global _FONT_CACHE
    if _FONT_CACHE is None:
        _FONT_CACHE = (
            ImageFont.truetype(FONT_PATH, 32),
            ImageFont.truetype(FONT_PATH, 26),
            ImageFont.truetype(FONT_PATH, 22),
            ImageFont.truetype(FONT_PATH, 20),
        )
    return _FONT_CACHE


def _event_style(kind: str) -> tuple[str, str]:
    return EVENT_STYLE.get(kind, ("#555555", "#F7F7F7"))


def _text_width(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw) -> float:
    return draw.textlength(text, font=font)


def _wrap(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw, max_w: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        cur = ""
        for ch in paragraph:
            nxt = cur + ch
            if _text_width(nxt, font, draw) <= max_w:
                cur = nxt
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
    return lines or [""]


class _Canvas:
    def __init__(self) -> None:
        self.font_title, self.font_h2, self.font_body, self.font_sm = _fonts()
        self.img = Image.new("RGB", (WIDTH, 600), "white")
        self.draw = ImageDraw.Draw(self.img)
        self.y = PAD
        self.content_w = WIDTH - PAD * 2

    def _grow(self, need: int) -> None:
        if self.y + need <= self.img.height:
            return
        new_h = self.img.height
        while self.y + need > new_h:
            new_h += GROW_STEP
        bigger = Image.new("RGB", (WIDTH, new_h), "white")
        bigger.paste(self.img, (0, 0))
        self.img.close()
        self.img = bigger
        self.draw = ImageDraw.Draw(self.img)

    def line(self, text: str, font: ImageFont.FreeTypeFont, color: str = "#333333", indent: int = 0) -> None:
        max_w = self.content_w - indent
        for row in _wrap(text, font, self.draw, max_w):
            self._grow(LINE)
            self.draw.text((PAD + indent, self.y), row, font=font, fill=color)
            self.y += LINE if font != self.font_sm else LINE_SM

    def section(self, title: str) -> None:
        self.y += 12
        self._grow(LINE + 8)
        self.draw.rectangle([PAD, self.y + 4, PAD + 5, self.y + 30], fill="#597aa8")
        self.draw.text((PAD + 14, self.y), title, font=self.font_h2, fill="#333333")
        self.y += LINE + 8

    def legend(self) -> None:
        self._grow(LINE_SM + 8)
        x = PAD + 8
        for label, color in LEGEND_ITEMS:
            self.draw.rectangle([x, self.y + 6, x + 14, self.y + 20], fill=color)
            self.draw.text((x + 20, self.y + 2), label, font=self.font_sm, fill=color)
            x += _text_width(label, self.font_sm, self.draw) + 44
        self.y += LINE_SM + 10

    def event_row(self, time_rel: str, kind: str, player: str, indent: int = 0) -> None:
        fg, bg = _event_style(kind)
        display_kind = "缴械" if kind == "缴械点名" else kind
        row_h = LINE_SM + 4
        self._grow(row_h)
        x0 = PAD + indent
        x1 = WIDTH - PAD
        self.draw.rectangle([x0, self.y, x1, self.y + row_h], fill=bg)
        self.draw.rectangle([x0, self.y, x0 + 5, self.y + row_h], fill=fg)
        cy = self.y + 2
        self.draw.text((x0 + 12, cy), time_rel, font=self.font_sm, fill="#666666")
        tx = x0 + 12 + _text_width(f"{time_rel}  ", self.font_sm, self.draw)
        self.draw.text((tx, cy), display_kind, font=self.font_sm, fill=fg)
        tx += _text_width(f"{display_kind}  ", self.font_sm, self.draw)
        self.draw.text((tx, cy), player, font=self.font_sm, fill="#333333")
        self.y += row_h + 2

    def round_block(self, rnd: TransferRound) -> None:
        placer = rnd.weapon_placer
        placer_text = (
            f"{placer.name} · {placer.xf_name} · {placer.pid}（{placer.xf_type}）"
            if placer else "—"
        )
        if rnd.success_ms:
            success_text = f"传功生效 {rnd.success_rel}（{len(rnd.participants)} 人）"
            success_color = "#1B7A3D"
        else:
            success_text = f"未达成传功（仅 {len(rnd.participants)} 人）"
            success_color = "#B91C1C"
        header = (
            f"第 {rnd.round_index} 轮 · 缴械 {rnd.boss_disarm_rel} · 放武器 {rnd.weapon_placed_rel} · "
            f"{success_text} · 装置 {placer_text} · {rnd.expected_effect}（{rnd.effect_triggered}）"
        )
        header_lines = _wrap(header, self.font_body, self.draw, self.content_w - 16)
        box_h = len(header_lines) * LINE_SM + 16
        self._grow(box_h)
        y0 = self.y
        self.draw.rectangle([PAD, y0, WIDTH - PAD, y0 + box_h], fill="#eef3ff")
        cy = y0 + 8
        for row in header_lines:
            color = success_color if "传功生效" in row or "未达成" in row else "#1a3a6e"
            self.draw.text((PAD + 8, cy), row, font=self.font_body, fill=color)
            cy += LINE_SM
        self.y = y0 + box_h + 6

        for ev in rnd.timeline:
            indent = 16 if ev.kind in ("传功开始", "传功完成", "传功生效", "传功中断") else 0
            player = ev.detail or ev.player_name
            self.event_row(ev.rel, ev.kind, player, indent=indent)

    def wipe_box(self, lines: list[str]) -> None:
        self.y += 8
        box_lines: list[str] = []
        for text in lines:
            if not text:
                continue
            box_lines.extend(_wrap(text, self.font_body, self.draw, self.content_w - 32))
        if not box_lines:
            return
        box_h = len(box_lines) * LINE_SM + 24
        self._grow(box_h)
        x0, y0 = PAD, self.y
        x1, y1 = WIDTH - PAD, self.y + box_h
        self.draw.rectangle([x0, y0, x1, y1], fill="#fff8f0", outline="#f0d8b8")
        cy = y0 + 12
        for i, row in enumerate(box_lines):
            color = "#444444" if i == 0 else ("#c45c26" if i == 1 else "#555555")
            self.draw.text((PAD + 16, cy), row, font=self.font_body, fill=color)
            cy += LINE_SM
        self.y = y1 + 8

    def footer(self, text: str) -> None:
        self.y += 16
        self._grow(LINE + 20)
        self.draw.rectangle([PAD, self.y, WIDTH - PAD, self.y + LINE + 16], fill="#f0f0f0")
        self.draw.text((PAD + 12, self.y + 8), text, font=self.font_sm, fill="#777777")
        self.y += LINE + 24

    def save(self) -> str:
        cropped = self.img.crop((0, 0, WIDTH, self.y + PAD))
        self.img.close()
        self.img = cropped
        out = build_path(CACHE, [get_uuid() + ".png"])
        cropped.save(out, optimize=True, compress_level=6)
        cropped.close()
        return out


def _build_canvas(data: LGZAnalysisResult, file_name: str, saohua: str) -> _Canvas:
    cv = _Canvas()
    cv.line("柳公子 · 传功与团灭分析", cv.font_title, "#222222")
    cv.line(
        f"{file_name} | {data.server} | {data.map_name} | 时长 {data.wipe.battle_duration_rel} | 传功 {len(data.rounds)} 轮",
        cv.font_sm,
        "#666666",
    )

    cv.section("传功轮次记录")
    cv.legend()
    if data.rounds:
        for rnd in data.rounds:
            cv.round_block(rnd)
    else:
        cv.line("未检测到传功轮次", cv.font_body, "#666666")

    cv.section("团灭分析")
    wipe = data.wipe
    if wipe.is_wipe:
        if wipe.category == "传功团灭":
            detail = wipe.detail
            if wipe.transfer_reasons:
                detail += f"（{'、'.join(wipe.transfer_reasons)}）"
        else:
            detail = f"造成团灭的伤害：{wipe.damage_source}"
    else:
        detail = wipe.detail

    cv.wipe_box([
        f"是否团灭：{'是' if wipe.is_wipe else '否'} · 类型：{wipe.category} · "
        f"爆发时刻：{wipe.wipe_rel} · 3秒内重伤：{wipe.wipe_count} 人",
        detail,
        wipe.damage_summary if wipe.is_wipe else "",
    ])

    cv.footer(f"柳公子 JCL 本地分析 | Inkar-Suki：{saohua}")
    return cv


async def render_lgz_image(data: LGZAnalysisResult, file_name: str, saohua: str):
    check_memory_available()
    cv = _build_canvas(data, file_name, saohua)
    path = cv.save()
    del cv
    gc.collect()
    img_bytes = Path(path).read_bytes()
    return ms.image(img_bytes)

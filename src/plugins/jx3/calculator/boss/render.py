"""通用 Boss DPS/HPS 榜单图（Pillow）."""

from __future__ import annotations

import gc
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from nonebot.adapters.onebot.v11 import MessageSegment as ms

from src.const.jx3.kungfu import Kungfu
from src.const.path import ASSETS, CACHE, build_path
from src.utils.generate import get_uuid

from ..lgz.parser import check_memory_available
from .compute import BossFightResult, BossPlayerStat

WIDTH = 1200
PAD = 28
GROW_STEP = 512
FONT_PATH = build_path(ASSETS, ["font", "PingFangSC-Semibold.otf"])
STAT_COL_W = 240

_SECTIONS = (
    ("DPS 榜单", "dps", "total_damage", "#2c7be5"),
    ("HPS 榜单", "hps", "total_heal", "#3ccd48"),
)


def _text_width(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw) -> float:
    return draw.textlength(text, font=font)


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    bbox = font.getbbox("国")
    return bbox[3] - bbox[1] + 8


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
        self.font_title = ImageFont.truetype(FONT_PATH, 32)
        self.font_head = ImageFont.truetype(FONT_PATH, 24)
        self.font_body = ImageFont.truetype(FONT_PATH, 20)
        self.font_sm = ImageFont.truetype(FONT_PATH, 18)
        self.img = Image.new("RGB", (WIDTH, 600), "#ffffff")
        self.draw = ImageDraw.Draw(self.img)
        self.y = PAD
        self.content_w = WIDTH - PAD * 2

    def _grow(self, need: int) -> None:
        if self.y + need <= self.img.height:
            return
        new_h = self.img.height
        while self.y + need > new_h:
            new_h += GROW_STEP
        bigger = Image.new("RGB", (WIDTH, new_h), "#ffffff")
        bigger.paste(self.img, (0, 0))
        self.img.close()
        self.img = bigger
        self.draw = ImageDraw.Draw(self.img)

    def line(self, text: str, font: ImageFont.FreeTypeFont, color: str = "#333333") -> None:
        lh = _line_height(font)
        for row in _wrap(text, font, self.draw, self.content_w):
            self._grow(lh)
            self.draw.text((PAD, self.y), row, font=font, fill=color)
            self.y += lh

    def section(self, title: str) -> None:
        self.y += 12
        bar_h = _line_height(self.font_head) + 12
        self._grow(bar_h + 8)
        self.draw.rectangle([PAD, self.y, WIDTH - PAD, self.y + bar_h], fill="#37d5ca")
        self.draw.text((PAD + 12, self.y + 6), title, font=self.font_head, fill="#ffffff")
        self.y += bar_h + 8

    def rank_rows(
        self,
        players: list[BossPlayerStat],
        rate_key: str,
        total_key: str,
        bar_color: str,
        anonymous: bool,
    ) -> None:
        ranked = sorted(players, key=lambda p: -getattr(p, rate_key))
        top = [p for p in ranked if getattr(p, rate_key) > 0]
        if not top:
            self.line("（无数据）", self.font_sm, "#888888")
            return

        label_h = _line_height(self.font_body)
        bar_h = 10
        row_h = label_h + bar_h + 10
        max_rate = max(getattr(p, rate_key) for p in top) or 1
        stat_x = WIDTH - PAD - STAT_COL_W

        for i, p in enumerate(top, 1):
            name = "匿名玩家" if anonymous else p.name
            try:
                kf = Kungfu.with_internel_id(p.xf_id, True)
                xf = kf.name or str(p.xf_id)
            except Exception:
                xf = str(p.xf_id)
            rate = getattr(p, rate_key)
            total = getattr(p, total_key)
            self._grow(row_h)
            y0 = self.y
            label = f"#{i}  {name}  ·  {xf}"
            self.draw.text((PAD + 4, y0), label, font=self.font_body, fill="#333333")
            stat = f"{total:,}  |  {rate:,}/s"
            self.draw.text((stat_x, y0), stat, font=self.font_sm, fill="#555555")
            bar_x = PAD + 4
            bar_w = stat_x - bar_x - 16
            bar_y = y0 + label_h + 2
            self.draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill="#eef2f6")
            fw = int(bar_w * rate / max_rate)
            if fw > 0:
                self.draw.rectangle([bar_x, bar_y, bar_x + fw, bar_y + bar_h], fill=bar_color)
            self.y += row_h

    def footer(self, text: str) -> None:
        self.y += 12
        lh = _line_height(self.font_sm)
        rows = _wrap(text, self.font_sm, self.draw, self.content_w - 16)
        box_h = lh * len(rows) + 16
        self._grow(box_h + 8)
        self.draw.rectangle([PAD, self.y, WIDTH - PAD, self.y + box_h], fill="#f0f0f0")
        ty = self.y + 8
        for row in rows:
            self.draw.text((PAD + 12, ty), row, font=self.font_sm, fill="#777777")
            ty += lh
        self.y += box_h + 8

    def save(self) -> str:
        out = build_path(CACHE, [get_uuid() + ".png"])
        cropped = self.img.crop((0, 0, WIDTH, self.y + PAD))
        cropped.save(out, optimize=True, compress_level=6)
        self.img.close()
        cropped.close()
        return out


def _build_canvas(data: BossFightResult, file_name: str, saohua: str, anonymous: bool) -> _Canvas:
    cv = _Canvas()
    assert data.meta.battle is not None
    title = f"{data.meta.boss_name} 战斗统计"
    cv.line(title, cv.font_title, "#222222")
    cv.line(
        f"{file_name} | {data.meta.server} | {data.meta.dungeon} | "
        f"{data.battle_time:.1f}s | 区间：{data.meta.battle.source}",
        cv.font_sm,
        "#666666",
    )
    cv.line(
        f"团队 DPS {data.team_dps:,}/s  ·  HPS {data.team_hps:,}/s",
        cv.font_sm,
        "#444444",
    )
    for section_title, rate_key, total_key, color in _SECTIONS:
        cv.section(section_title)
        cv.rank_rows(data.players, rate_key, total_key, color, anonymous)
    cv.footer(f"Boss JCL 本地 DPS/HPS · jx3bla 统计 | Inkar-Suki：{saohua}")
    return cv


async def render_boss_image(data: BossFightResult, file_name: str, saohua: str, anonymous: bool = False):
    check_memory_available()
    cv = _build_canvas(data, file_name, saohua, anonymous)
    path = cv.save()
    del cv
    gc.collect()
    return ms.image(Path(path).read_bytes())

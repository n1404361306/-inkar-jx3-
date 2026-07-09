"""本实例可用功能菜单（随 config 动态生成，返回图片）."""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

from src.config import Config
from src.utils.generate import generate

MenuMatcher = on_command("menu", aliases={"菜单"}, force_whitespace=True, priority=5)


@dataclass
class MenuSection:
    title: str
    items: list[str] = field(default_factory=list)
    columns: int = 5


@dataclass
class MenuGroup:
    title: str
    items: list[str]


def _lines(*items: str) -> list[str]:
    return [item for item in items if item]


def build_menu_sections() -> list[MenuSection]:
    sections: list[MenuSection] = []

    sections.append(
        MenuSection(
            "基础",
            _lines(
                "ping",
                "菜单",
                "关于",
                "查看授权",
                "授权 天数",
                "绑定 / 绑定区服",
                "绑定角色",
                "解绑角色",
                "角色列表",
                "提交角色",
                "偏好",
                "重置偏好",
                "wiki",
                "iwiki",
                "订阅 / 退订",
                "反馈",
                "inkar help",
                "签到 / 抽签",
                "金币",
                "喜报 / 悲报",
                "24点",
                "对诗",
                "猜成语",
                "答案之书",
                "吃什么",
                "喝什么",
                "BMI",
                "黑名单",
                "避雷",
                "本群发言统计",
            ),
        )
    )
    return sections


def build_jx3_groups() -> list[MenuGroup]:
    return [
        MenuGroup(
            "日常",
            _lines(
                "招募",
                "日常",
                "版本",
                "体服版本",
                "公告",
                "体服公告",
                "技改",
                "开服",
                "金价",
                "剑三黄历",
                "科举",
                "副本",
                "副本列表",
                "掉落列表",
                "全服掉落",
                "百战",
                "精耐*",
            ),
        ),
        MenuGroup(
            "交易",
            _lines(
                "物价",
                "交易行",
                "交易行v2",
                "交易行v3",
                "交易行试炼",
                "交易行试炼v2",
                "交易行试炼v3",
                "万宝楼",
                "蹲号",
                "贴吧物价",
            ),
        ),
        MenuGroup(
            "奇遇",
            _lines(
                "奇遇",
                "奇遇v2",
                "奇遇v3",
                "宠物奇遇",
                "前置 / 攻略",
                "奇遇时间",
            ),
        ),
        MenuGroup(
            "角色",
            _lines(
                "属性 / 查装",
                "配装",
                "装备",
                "附魔",
                "宏",
                "阵眼",
                "奇穴",
                "技能",
                "buff",
                "名片*",
                "战绩",
                "玩家",
                "查人 / 骗子",
                "抓马 / 马场",
                "沙盘",
                "烟花",
                "小药",
            ),
        ),
        MenuGroup(
            "其他",
            _lines(
                "楚天社",
                "云从社",
                "披风会",
                "诛恶",
                "骚话",
                "舔狗",
                "黑本",
                "翻牌",
                "抽奇遇",
                "抽装备",
                "绑定情缘",
                "查看情缘证书",
                "解密",
                "报点",
            ),
        ),
        MenuGroup(
            "排行",
            _lines(
                "团队排名",
                "名人堂",
                "资历排行",
                "RD天梯",
                "RH天梯",
                "HPS排行榜",
                "试炼之地",
                "唐怀仁大C榜",
                "唐怀仁大吸榜",
                "池清川大C榜",
                "池清川大吸榜",
            ),
        ),
    ]


def build_jcl_items() -> list[str]:
    api = Config.jx3.api
    items = ["THR-*.jcl", "BOSS-*.jcl", "LGZ-*.jcl"]
    if api.bla_url:
        items += ["BLA-*.jcl", "TRD-*.jcl"]
    if api.cqc_url:
        items += ["CQC-*.jcl", "FAL-*.jcl", "YXC-*.jcl", "ROD-*.jcl", "ASN-*.jcl"]
    items.append("JCL分析 help")
    return items


def build_calculator_items() -> list[str]:
    return _lines(
        "计算器",
        "装备对比",
        "装备评级",
        "治疗面板",
        "循环曲线",
        "循环对比",
        "循环k线",
        "循环k线游戏",
        "自定义循环 help",
        "计算器支持",
        "装备评级支持",
        "RD分析支持",
    )


SECTION_THEMES: dict[str, str] = {
    "基础": "sky",
    "剑网三": "gold",
    "JCL 群文件": "teal",
    "计算器": "violet",
    "天气": "cyan",
    "附加订阅": "rose",
}

JX3_GROUP_THEMES: dict[str, str] = {
    "日常": "amber",
    "交易": "emerald",
    "奇遇": "purple",
    "角色": "blue",
    "其他": "rose",
    "排行": "orange",
}


def _render_items(items: list[str], columns: int = 3, tone: str = "default") -> str:
    cells = "".join(
        f'<div class="item tone-{tone}">{html.escape(item)}</div>'
        for item in items
    )
    return f'<div class="grid" style="grid-template-columns:repeat({columns},1fr)">{cells}</div>'


def _render_section(section: MenuSection, tone: str | None = None) -> str:
    theme = tone or SECTION_THEMES.get(section.title, "sky")
    return (
        f'<section class="section tone-{theme}">'
        f'<div class="section-title"><span class="dot"></span>{html.escape(section.title)}</div>'
        f'{_render_items(section.items, section.columns, theme)}'
        f"</section>"
    )


def _render_jx3_block(groups: list[MenuGroup]) -> str:
    blocks = []
    for group in groups:
        theme = JX3_GROUP_THEMES.get(group.title, "gold")
        blocks.append(
            f'<div class="sub tone-{theme}">'
            f'<div class="sub-title"><span class="dot"></span>{html.escape(group.title)}</div>'
            f'{_render_items(group.items, 3, theme)}'
            f"</div>"
        )
    return (
        f'<section class="section tone-gold jx3-section">'
        f'<div class="section-title"><span class="dot"></span>剑网三</div>'
        f'<div class="jx3-grid">{"".join(blocks)}</div>'
        f"</section>"
    )


def _render_pair(
    left_title: str,
    left_items: list[str],
    right_title: str,
    right_items: list[str],
) -> str:
    left_theme = SECTION_THEMES.get(left_title, "teal")
    right_theme = SECTION_THEMES.get(right_title, "violet")
    return (
        f'<section class="section pair">'
        f'<div class="pair-col tone-{left_theme}">'
        f'<div class="section-title"><span class="dot"></span>{html.escape(left_title)}</div>'
        f'{_render_items(left_items, 3, left_theme)}'
        f"</div>"
        f'<div class="pair-col tone-{right_theme}">'
        f'<div class="section-title"><span class="dot"></span>{html.escape(right_title)}</div>'
        f'{_render_items(right_items, 3, right_theme)}'
        f"</div>"
        f"</section>"
    )


def _menu_styles() -> str:
    return """
body {
  margin: 0;
  background: linear-gradient(160deg, #e8eef8 0%, #f3e8ff 38%, #fef3e2 100%);
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #1e293b;
}
.page {
  width: 680px;
  box-sizing: border-box;
  padding: 14px;
}
.header {
  position: relative;
  overflow: hidden;
  text-align: center;
  padding: 14px 16px 12px;
  background: linear-gradient(125deg, #1a1f4b 0%, #3b1f5c 42%, #7c2d3a 100%);
  color: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(59, 31, 92, 0.28);
}
.header::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 12% 18%, rgba(255, 214, 120, 0.28), transparent 34%),
    radial-gradient(circle at 88% 12%, rgba(120, 196, 255, 0.22), transparent 30%),
    radial-gradient(circle at 70% 88%, rgba(255, 120, 150, 0.18), transparent 36%);
  pointer-events: none;
}
.title {
  position: relative;
  font-size: 21px;
  font-weight: 900;
  letter-spacing: 0.8px;
  background: linear-gradient(90deg, #fff 0%, #ffe7a3 45%, #ffd0dc 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.subtitle {
  position: relative;
  margin-top: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.78);
}
.section {
  margin-top: 9px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.85);
  border-radius: 10px;
  padding: 9px 10px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
}
.section.compact { padding: 7px 10px; }
.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 800;
  color: #334155;
  margin-bottom: 6px;
}
.section-title .dot,
.sub-title .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.85);
}
.grid { display: grid; gap: 4px 5px; }
.item {
  font-size: 10.5px;
  line-height: 1.25;
  border-radius: 5px;
  padding: 3px 4px;
  text-align: center;
  word-break: break-all;
  border: 1px solid transparent;
  transition: none;
}
.jx3-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px 8px; }
.sub {
  border-radius: 8px;
  padding: 6px 7px;
  border: 1px solid rgba(255, 255, 255, 0.7);
}
.sub-title {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 800;
  margin-bottom: 5px;
}
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: transparent; border: none; box-shadow: none; padding: 0; }
.pair-col {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.85);
  border-radius: 10px;
  padding: 8px 9px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
}
.pair-col.tone-teal { background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(240,253,250,0.88)); border-color: #99f6e4; }
.pair-col.tone-violet { background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(245,243,255,0.88)); border-color: #ddd6fe; }
.pair-col .section-title { margin-bottom: 5px; }
.footer {
  margin-top: 9px;
  padding: 8px 10px;
  font-size: 9.5px;
  color: #5b6478;
  line-height: 1.45;
  text-align: center;
  background: rgba(255, 255, 255, 0.72);
  border: 1px dashed rgba(148, 163, 184, 0.45);
  border-radius: 8px;
}

.tone-sky .section-title .dot, .tone-sky.sub-title .dot { background: #38bdf8; }
.item.tone-sky { color: #0c4a6e; background: linear-gradient(180deg, #f0f9ff, #e0f2fe); border-color: #bae6fd; }
.tone-gold .section-title .dot, .tone-gold.sub-title .dot { background: #f59e0b; }
.tone-gold.sub { background: linear-gradient(180deg, rgba(255, 251, 235, 0.95), rgba(254, 243, 199, 0.55)); border-color: #fde68a; }
.item.tone-gold { color: #78350f; background: linear-gradient(180deg, #fffbeb, #fef3c7); border-color: #fcd34d; }
.tone-amber .sub-title { color: #92400e; }
.tone-amber .sub-title .dot { background: #f59e0b; }
.item.tone-amber { color: #78350f; background: linear-gradient(180deg, #fff7ed, #ffedd5); border-color: #fdba74; }
.tone-emerald .sub-title { color: #065f46; }
.tone-emerald .sub-title .dot { background: #10b981; }
.item.tone-emerald { color: #064e3b; background: linear-gradient(180deg, #ecfdf5, #d1fae5); border-color: #6ee7b7; }
.tone-purple .sub-title { color: #5b21b6; }
.tone-purple .sub-title .dot { background: #a855f7; }
.item.tone-purple { color: #4c1d95; background: linear-gradient(180deg, #faf5ff, #ede9fe); border-color: #c4b5fd; }
.tone-blue .sub-title { color: #1d4ed8; }
.tone-blue .sub-title .dot { background: #3b82f6; }
.item.tone-blue { color: #1e3a8a; background: linear-gradient(180deg, #eff6ff, #dbeafe); border-color: #93c5fd; }
.tone-rose .sub-title, .tone-rose .section-title { color: #9f1239; }
.tone-rose .sub-title .dot, .tone-rose .section-title .dot { background: #f43f5e; }
.item.tone-rose { color: #881337; background: linear-gradient(180deg, #fff1f2, #ffe4e6); border-color: #fda4af; }
.tone-orange .sub-title { color: #9a3412; }
.tone-orange .sub-title .dot { background: #f97316; }
.item.tone-orange { color: #7c2d12; background: linear-gradient(180deg, #fff7ed, #ffedd5); border-color: #fdba74; }
.tone-teal .section-title .dot { background: #14b8a6; }
.item.tone-teal { color: #115e59; background: linear-gradient(180deg, #f0fdfa, #ccfbf1); border-color: #5eead4; }
.tone-violet .section-title .dot { background: #8b5cf6; }
.item.tone-violet { color: #4c1d95; background: linear-gradient(180deg, #f5f3ff, #ede9fe); border-color: #c4b5fd; }
.tone-cyan .section-title .dot { background: #06b6d4; }
.item.tone-cyan { color: #155e75; background: linear-gradient(180deg, #ecfeff, #cffafe); border-color: #67e8f9; }

.jx3-section {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(255, 251, 235, 0.72));
  border-color: #fde68a;
}
.jx3-section > .section-title { color: #92400e; }
"""


def _build_footer_notes() -> str:
    api = Config.jx3.api
    ws = Config.jx3.ws
    notes = [
        "* 精耐、名片等需群权限",
        "吃什么/喝什么支持「今天吃什么」等说法",
        "上传 JCL 群文件可自动分析",
        "文档：inkar-suki.codethink.cn",
    ]
    if api.enable and not ws.enable:
        notes.insert(0, "JX3API 推送未配置 WebSocket，订阅可用但不会推送")
    return " · ".join(notes)


async def render_menu_image() -> Message:
    bot = Config.bot_basic.bot_name
    body_parts: list[str] = []

    for section in build_menu_sections():
        body_parts.append(_render_section(section))

    if Config.jx3.api.enable:
        body_parts.append(_render_jx3_block(build_jx3_groups()))

        jcl_items = build_jcl_items()
        if Config.jx3.api.calculator_url:
            body_parts.append(
                _render_pair("JCL 群文件", jcl_items, "计算器", build_calculator_items())
            )
        else:
            body_parts.append(
                f'<section class="section tone-teal">'
                f'<div class="section-title"><span class="dot"></span>JCL 群文件</div>'
                f'{_render_items(jcl_items, 4, "teal")}'
                f"</section>"
            )

    if Config.weather.token:
        body_parts.append(
            f'<section class="section compact tone-cyan">'
            f'<div class="section-title"><span class="dot"></span>天气</div>'
            f'{_render_items(["天气 城市名"], 1, "cyan")}'
            f"</section>"
        )

    body_parts.append(
        f'<section class="section compact tone-rose">'
        f'<div class="section-title"><span class="dot"></span>附加订阅</div>'
        f'{_render_items(["订阅 开团", "订阅 抽奖", "订阅 招募过滤", "订阅 抽情缘", "更多见：关于"], 5, "rose")}'
        f"</section>"
    )

    html_source = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
{_menu_styles()}
</style></head><body>
<div class="page">
  <div class="header">
    <div class="title">{html.escape(bot)} · 功能菜单</div>
    <div class="subtitle">发送「菜单」查看 · 当前实例已启用功能</div>
  </div>
  {"".join(body_parts)}
  <div class="footer">{html.escape(_build_footer_notes())}</div>
</div></body></html>"""
    return await generate(
        html_source,
        ".page",
        segment=True,
        viewport={"width": 720, "height": 800},
    )


@MenuMatcher.handle()
async def _(args: Message = CommandArg()):
    if args.extract_plain_text().strip() != "":
        return
    await MenuMatcher.finish(await render_menu_image())

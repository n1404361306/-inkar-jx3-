"""本实例可用功能菜单（随 config 动态生成）."""

from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

from src.config import Config

MenuMatcher = on_command("menu", aliases={"菜单"}, force_whitespace=True, priority=5)


def _lines(*items: str) -> list[str]:
    return [item for item in items if item]


def _section(title: str, lines: list[str]) -> str:
    if not lines:
        return ""
    body = "\n".join(f"· {line}" for line in lines)
    return f"\n【{title}】\n{body}"


def build_instance_menu() -> str:
    api = Config.jx3.api
    ws = Config.jx3.ws
    bot = Config.bot_basic.bot_name

    sections: list[str] = [
        f"【{bot} · 功能菜单】",
        "以下为当前实例已启用、可正常使用的功能。",
    ]

    sections.append(
        _section(
            "基础",
            _lines(
                "ping — 测试机器人在线",
                "菜单 — 查看本列表",
                "关于 — 本群订阅与附加功能",
                "查看授权 / 授权 天数 — 群授权（最多 30 天）",
                "绑定 区服 — 绑定本群默认区服（管理员）",
                "绑定角色 / 解绑角色 / 角色列表 — 个人角色",
                "提交角色 服务器 UID — 提交角色数据",
                "偏好 / 重置偏好 — 个人偏好",
                "wiki / iwiki — Wiki 查询",
                "订阅 / 退订 — 开启或关闭群功能",
                "反馈 内容 — 问题反馈（至少 8 字）",
                "inkar help — 帮助指令索引（图片）",
                "签到 / 抽签 / 金币 — 签到与抽签",
                "喜报 / 悲报 — 生成喜报悲报图",
                "24点 / 对诗 / 猜成语 / 答案之书 — 趣味互动",
                "今天吃什么 / 今天喝什么 — 随机推荐",
                "BMI 身高 体重 — 身体质量指数",
                "黑名单 / 避雷 — 群黑名单管理",
                "本群发言统计 — 今日发言统计",
            ),
        )
    )

    if api.enable:
        jx3 = _lines(
            "招募 [表达式] — 团队招募（&且 |或 ,或 支持括号）",
            "日常 — 今日日常",
            "版本 / 体服版本 — 客户端版本",
            "公告 / 体服公告 / 技改 — 维护与技改",
            "开服 — 开服维护状态",
            "金价 — 全服金价",
            "物价 / 物价v2 — 物品物价",
            "交易行 / 交易行v2 / 交易行v3 — 交易行查询",
            "交易行试炼 / 试炼v2 / 试炼v3 — 试炼模拟",
            "万宝楼 — 万宝楼角色",
            "奇遇 / 奇遇v2 / 奇遇v3 — 奇遇查询",
            "宠物奇遇 / 前置 / 攻略 — 奇遇相关",
            "奇遇时间 — 提交奇遇时间",
            "科举 — 科举答题",
            "剑三黄历 — 今日黄历",
            "副本 / 副本列表 — 副本进度",
            "掉落列表 / 全服掉落 — 掉落记录",
            "百战 / 精耐 — 百战与精耐（精耐需群权限）",
            "属性 / 查装 — 角色属性",
            "配装 / 装备 / 附魔 — 装备查询",
            "宏 / 阵眼 / 奇穴 / 技能 / buff — 技能资料",
            "名片 — 角色名片（需群权限）",
            "战绩 — 竞技场战绩",
            "玩家 / 玩家信息 — 玩家资料",
            "查人 / 骗子 — 骗子查询",
            "抓马 / 马场 — 马场刷新",
            "沙盘 — 阵营沙盘",
            "烟花 — 烟花活动",
            "小药 — 门派小药",
            "蹲号 / 贴吧物价 — 交易信息",
            "楚天社 / 云从社 / 披风会 / 诛恶 — 活动查询",
            "骚话 / 舔狗 — 随机文案",
            "黑本 / 翻牌 / 抽奇遇 / 抽装备 — 模拟玩法",
            "绑定情缘 / 查看情缘证书 — 情缘证书",
            "团队排名 / 名人堂 / 资历排行 — 排行榜",
            "RD天梯 / RH天梯 / HPS排行榜 — 心法排行",
            "试炼之地 — 试炼排行",
            "唐怀仁大C榜 / 唐怀仁大吸榜 — 唐怀仁榜",
            "池清川大C榜 / 池清川大吸榜 — 池清川榜",
            "解密 / 报点 — 开团辅助解谜",
            "JCL分析 help — JCL 分析说明",
        )
        sections.append(_section("剑网三", jx3))

        jcl: list[str] = [
            "THR-*.jcl — 唐怀仁 P1 DPS/HPS（本地解析）",
            "BOSS-*.jcl — 任意首领全程 DPS/HPS 榜单（本地解析）",
            "LGZ-*.jcl — 柳公子传功与团灭分析（本地解析）",
        ]
        if api.bla_url:
            jcl += [
                "BLA-*.jcl — 单 BOSS RDPS/RHPS（剑三警长）",
                "TRD-*.jcl — 唐怀仁 P1 RDPS（剑三警长）",
            ]
        if api.cqc_url:
            jcl += [
                "CQC- / FAL- / YXC- / ROD- — 各类 JCL 专项分析",
                "ASN- / THF- / LNX- / CAL- — 首领专项分析",
            ]
        sections.append(_section("JCL 群文件分析", jcl))

        if api.calculator_url:
            sections.append(
                _section(
                    "计算器",
                    _lines(
                        "计算器 — DPS 循环计算",
                        "装备对比 — 装备循环对比",
                        "装备评级 — 装备评分",
                        "治疗面板 — 治疗循环面板",
                        "循环曲线 / 循环对比 — 伤害时间轴",
                        "循环k线游戏 — K 线小游戏",
                        "自定义循环 help — 自定义循环说明",
                        "计算器支持 / 装备评级支持 — 支持心法列表",
                        "RD分析支持 — RD 分析说明",
                    ),
                )
            )

        if not ws.enable:
            sections.append(
                "\n【说明】JX3API 主动推送（818、公告、日常等）未配置 WebSocket，"
                "订阅命令可用但不会收到推送。"
            )
        elif api.weibo:
            sections.append("\n【说明】已启用微博相关订阅（如「咸鱼」）。")

    if Config.weather.token:
        sections.append(_section("天气", ["天气 城市名 — 查询城市天气"]))

    sections.append(
        _section(
            "附加功能（需订阅开启）",
            _lines(
                "订阅 开团 — 开团辅助（创建团队、预定等）",
                "订阅 抽奖 — 禁言抽奖",
                "订阅 招募过滤 — 招募广告过滤",
                "订阅 抽情缘 — 随机情缘",
                "更多见：关于",
            ),
        )
    )

    sections.append(
        "\n上传 JCL：将符合命名规则的 .jcl 文件发到群文件即可自动分析。"
        "\n详细文档：https://inkar-suki.codethink.cn/Inkar-Suki-Docs/#/usage"
    )
    return "\n".join(part for part in sections if part)


@MenuMatcher.handle()
async def _(args: Message = CommandArg()):
    if args.extract_plain_text().strip() != "":
        return
    await MenuMatcher.finish(build_instance_menu())

#!/usr/bin/env python3
"""轻量 ASN 解析测试（不加载 NoneBot / Playwright）."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _stub_packages():
    for name in (
        "src",
        "src.plugins",
        "src.plugins.jx3",
        "src.plugins.jx3.calculator",
        "src.plugins.jx3.calculator.asn",
        "src.plugins.jx3.calculator.lgz",
        "src.const",
        "src.const.jx3",
    ):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []  # type: ignore[attr-defined]
            sys.modules[name] = mod


def main() -> None:
    _stub_packages()
    jcl = ROOT / "testdata/ASN-2026-06-01-21-10-10-25人英雄阆风悬城(795)-阿史那承庆(137130).jcl"
    if not jcl.exists():
        print("skip: test jcl missing")
        return

    for rel in (
        "src/plugins/jx3/calculator/lgz/lua_table.py",
        "src/plugins/jx3/calculator/lgz/parser.py",
        "src/plugins/jx3/calculator/asn/parser.py",
        "src/plugins/jx3/calculator/asn/compute.py",
    ):
        name = rel.replace("/", ".").replace(".py", "")
        sp = importlib.util.spec_from_file_location(name, ROOT / rel)
        mod = importlib.util.module_from_spec(sp)
        sys.modules[name] = mod
        sp.loader.exec_module(mod)

    compute = sys.modules["src.plugins.jx3.calculator.asn.compute"]
    result = compute.compute_asn(str(jcl))
    print(f"server={result.meta.server} boss={result.meta.boss_id}")
    print(f"汲取波次: {len(result.jiqu_waves)}  死侍轮次: {len(result.dead_rounds)}")

    for wave in result.jiqu_waves:
        print(f"\n=== 第{wave.index}波汲取 @{wave.start_rel} ===")
        for rank, e in enumerate(wave.qte_po[:8], 1):
            bad = e.extra.get("bad", 0)
            print(f"  #{rank} {e.name}: 破{e.value} 碎{bad}")

    for rnd in result.dead_rounds:
        print(f"\n=== 第{rnd.index}轮死侍 @{rnd.start_rel} ({rnd.servant_count}人) ===")
        for rank, e in enumerate(rnd.shield_heal[:8], 1):
            print(f"  #{rank} {e.name}: 索命期间治疗 {e.value:,}")
            skills: dict[int, list[int]] = e.extra.get("skills", {})
            for skill_id, values in sorted(skills.items(), key=lambda x: -sum(x[1]))[:5]:
                from src.plugins.jx3.calculator.lgz.parser import skill_display_name

                print(
                    f"      - {skill_display_name(int(skill_id))}: "
                    f"{len(values)}次 / {sum(values):,}"
                )

    print("\nOK")


if __name__ == "__main__":
    main()

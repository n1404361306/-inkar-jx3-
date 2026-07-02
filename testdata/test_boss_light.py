#!/usr/bin/env python3
"""Light test for BOSS- generic DPS/HPS analysis (no NoneBot)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _stub_packages() -> None:
    for name in (
        "src",
        "src.plugins",
        "src.plugins.jx3",
        "src.plugins.jx3.calculator",
        "src.plugins.jx3.calculator.boss",
        "src.plugins.jx3.calculator.lgz",
    ):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []  # type: ignore[attr-defined]
            sys.modules[name] = mod


def main() -> None:
    _stub_packages()
    jcl = ROOT / "testdata" / "LGZ-2026-05-13-22-41-46-25人英雄阆风悬城(795)-柳公子(137135).jcl"
    file_name = "2026-05-13-22-41-46-25人英雄阆风悬城(795)-柳公子(137135).jcl"
    if not jcl.exists():
        print("skip: test jcl missing")
        return

    for rel in (
        "src/plugins/jx3/calculator/lgz/lua_table.py",
        "src/plugins/jx3/calculator/lgz/parser.py",
        "src/plugins/jx3/calculator/boss/parser.py",
        "src/plugins/jx3/calculator/boss/compute.py",
    ):
        name = rel.replace("/", ".").replace(".py", "")
        sp = importlib.util.spec_from_file_location(name, ROOT / rel)
        mod = importlib.util.module_from_spec(sp)
        sys.modules[name] = mod
        sp.loader.exec_module(mod)

    compute = sys.modules["src.plugins.jx3.calculator.boss.compute"]
    data = compute.compute_boss_fight(str(jcl), file_name)
    assert data.meta.battle is not None
    print(f"boss={data.meta.boss_name} time={data.battle_time:.1f}s source={data.meta.battle.source}")
    print(f"team_dps={data.team_dps} team_hps={data.team_hps}")
    for p in data.players[:8]:
        if p.dps > 0 or p.hps > 0:
            print(f"  {p.name}: dps={p.dps} hps={p.hps}")
    assert any(p.dps > 0 for p in data.players), "expected dps data"
    print("OK")


if __name__ == "__main__":
    main()

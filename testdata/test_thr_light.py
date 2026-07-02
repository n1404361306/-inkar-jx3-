#!/usr/bin/env python3
"""轻量 THR 解析测试（不加载 NoneBot / Playwright）."""

import gc
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/root/jx3bla")


def _stub_packages():
    for name in (
        "src",
        "src.plugins",
        "src.plugins.jx3",
        "src.plugins.jx3.calculator",
        "src.plugins.jx3.calculator.lgz",
        "src.plugins.jx3.calculator.thr",
        "src.const",
        "src.const.jx3",
    ):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []  # type: ignore[attr-defined]
            sys.modules[name] = mod


def main() -> None:
    _stub_packages()
    jcl = ROOT / "testdata/THR-2026-06-09-21-31-27-25人英雄阆风悬城(795)-须罗巨傀(137175).jcl"
    if not jcl.exists():
        print("skip: test jcl missing")
        return

    spec = importlib.util.spec_from_file_location(
        "thr_compute",
        ROOT / "src/plugins/jx3/calculator/thr/compute.py",
    )
    # load dependencies in order
    for rel in (
        "src/plugins/jx3/calculator/lgz/lua_table.py",
        "src/plugins/jx3/calculator/lgz/parser.py",
        "src/plugins/jx3/calculator/thr/parser.py",
        "src/plugins/jx3/calculator/thr/compute.py",
    ):
        name = rel.replace("/", ".").replace(".py", "")
        sp = importlib.util.spec_from_file_location(name, ROOT / rel)
        mod = importlib.util.module_from_spec(sp)
        sys.modules[name] = mod
        sp.loader.exec_module(mod)

    compute = sys.modules["src.plugins.jx3.calculator.thr.compute"]
    print("computing…")
    result = compute.compute_thr_p1(str(jcl))
    print(f"P1 {result.battle_time:.1f}s shout={result.end_shout[:24]}…")
    print(f"team dps={result.team_dps:,} hps={result.team_hps:,}")
    for p in result.players[:5]:
        print(f"  {p.name}: dps={p.dps:,} hps={p.hps:,}")
    del result
    gc.collect()
    print("OK")


if __name__ == "__main__":
    main()

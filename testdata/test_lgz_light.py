#!/usr/bin/env python3
"""轻量 LGZ 解析测试（不加载 NoneBot / Playwright）."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_parser():
    # stub package path for relative import
    pkg_root = types.ModuleType("src")
    pkg_plugins = types.ModuleType("src.plugins")
    pkg_jx3 = types.ModuleType("src.plugins.jx3")
    pkg_calc = types.ModuleType("src.plugins.jx3.calculator")
    pkg_lgz = types.ModuleType("src.plugins.jx3.calculator.lgz")
    for name, mod in [
        ("src", pkg_root),
        ("src.plugins", pkg_plugins),
        ("src.plugins.jx3", pkg_jx3),
        ("src.plugins.jx3.calculator", pkg_calc),
        ("src.plugins.jx3.calculator.lgz", pkg_lgz),
    ]:
        sys.modules[name] = mod
        mod.__path__ = []  # type: ignore[attr-defined]

    lua_spec = importlib.util.spec_from_file_location(
        "src.plugins.jx3.calculator.lgz.lua_table",
        ROOT / "src/plugins/jx3/calculator/lgz/lua_table.py",
    )
    lua_mod = importlib.util.module_from_spec(lua_spec)
    sys.modules[lua_spec.name] = lua_mod
    lua_spec.loader.exec_module(lua_mod)

    kungfu_mod = types.ModuleType("src.const.jx3.kungfu")

    class Kungfu:
        _names = {}

        @classmethod
        def with_internel_id(cls, xf_id: int, _=True):
            from src.const.jx3.kungfu import Kungfu as RealKungfu  # noqa: F401

            obj = types.SimpleNamespace()
            try:
                real = RealKungfu.with_internel_id(xf_id, True)
                obj.name = real.name or str(xf_id)
            except Exception:
                obj.name = str(xf_id)
            return obj

    # 尝试真实 Kungfu，失败则用 ID
    try:
        from src.const.jx3.kungfu import Kungfu as RealKungfu

        kungfu_mod.Kungfu = RealKungfu
    except Exception:
        kungfu_mod.Kungfu = Kungfu

    sys.modules["src.const"] = types.ModuleType("src.const")
    sys.modules["src.const.jx3"] = types.ModuleType("src.const.jx3")
    sys.modules["src.const.jx3.kungfu"] = kungfu_mod

    parser_spec = importlib.util.spec_from_file_location(
        "src.plugins.jx3.calculator.lgz.parser",
        ROOT / "src/plugins/jx3/calculator/lgz/parser.py",
    )
    parser_mod = importlib.util.module_from_spec(parser_spec)
    sys.modules[parser_spec.name] = parser_mod
    parser_spec.loader.exec_module(parser_mod)
    return parser_mod


def main() -> None:
    mod = _load_parser()
    jcl = ROOT / "testdata/LGZ-e2e-test.jcl"
    if not jcl.exists():
        jcl = ROOT / "testdata/LGZ-2026-05-13-22-41-46-25人英雄阆风悬城(795)-柳公子(137135).jcl"
    data = mod.parse_lgz_jcl_path(str(jcl), file_name="LGZ-test.jcl")
    print(f"rounds={len(data.rounds)}")
    for r in data.rounds:
        kinds = [e.kind for e in r.timeline]
        assert "注视" not in kinds and "三叠扇注视" not in kinds
        print(
            f"  R{r.round_index}: success={r.success_rel}, n={len(r.participants)}, "
            f"effect={r.effect_triggered}, timeline={kinds}"
        )
    w = data.wipe
    print(f"wipe: {w.category} | {w.detail}")
    print(f"damage: {w.damage_source}")
    print(f"summary: {w.damage_summary}")
    assert w.category == "非传功团灭", w.category
    print("OK")


if __name__ == "__main__":
    main()

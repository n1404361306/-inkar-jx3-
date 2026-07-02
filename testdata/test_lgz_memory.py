#!/usr/bin/env python3
"""LGZ 内存占用测试（逐行读文件，不加载 Playwright）."""

import importlib.util
import resource
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _load_parser():
    for name, mod in [
        ("src", types.ModuleType("src")),
        ("src.plugins", types.ModuleType("src.plugins")),
        ("src.plugins.jx3", types.ModuleType("src.plugins.jx3")),
        ("src.plugins.jx3.calculator", types.ModuleType("src.plugins.jx3.calculator")),
        ("src.plugins.jx3.calculator.lgz", types.ModuleType("src.plugins.jx3.calculator.lgz")),
    ]:
        sys.modules[name] = mod

    lua_spec = importlib.util.spec_from_file_location(
        "src.plugins.jx3.calculator.lgz.lua_table",
        ROOT / "src/plugins/jx3/calculator/lgz/lua_table.py",
    )
    lua_mod = importlib.util.module_from_spec(lua_spec)
    sys.modules[lua_spec.name] = lua_mod
    lua_spec.loader.exec_module(lua_mod)

    try:
        from src.const.jx3.kungfu import Kungfu as RealKungfu
    except Exception:
        RealKungfu = None

    kungfu_mod = types.ModuleType("src.const.jx3.kungfu")
    if RealKungfu:
        kungfu_mod.Kungfu = RealKungfu
    else:
        class _K:
            @staticmethod
            def with_internel_id(xf_id, _=True):
                return types.SimpleNamespace(name=str(xf_id))
        kungfu_mod.Kungfu = _K

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

    print(f"start RSS={rss_mb():.0f}MB")
    data = mod.parse_lgz_jcl_path(str(jcl), file_name="LGZ-test.jcl")
    print(f"after parse RSS={rss_mb():.0f}MB events={data.meta.get('event_count')}")
    assert data.wipe.category == "非传功团灭"
    print("OK")


if __name__ == "__main__":
    main()

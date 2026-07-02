#!/usr/bin/env python3
"""LGZ 分析端到端测试：HTTP 拉取 JCL → 解析 → 生成图片."""

import asyncio
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

JCL_NAME = "LGZ-e2e-test.jcl"
JCL_DISPLAY = "LGZ-2026-05-13-22-41-46-25人英雄阆风悬城(795)-柳公子(137135).jcl"
PORT = 18765
OUT_IMG = Path(__file__).parent / "lgz_e2e_report.png"


def start_file_server(directory: Path) -> ThreadingHTTPServer:
    dir_str = str(directory)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, request, client_address, server):
            super().__init__(request, client_address, server, directory=dir_str)

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    t = Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


async def main() -> None:
    import nonebot

    nonebot.init()

    from src.plugins.jx3.calculator.jcl_analyze import LGZAnalyze
    from src.plugins.jx3.calculator.lgz.parser import parse_lgz_jcl
    from src.utils.generate import ScreenshotGenerator

    testdata = Path(__file__).parent
    jcl_path = testdata / JCL_NAME
    if not jcl_path.exists():
        jcl_path = testdata / JCL_DISPLAY
    if not jcl_path.exists():
        print("FAIL: JCL not found", jcl_path)
        sys.exit(1)

    server = start_file_server(testdata)
    url = f"http://127.0.0.1:{PORT}/{JCL_NAME}"

    # 解析校验
    raw = jcl_path.read_bytes()
    data = parse_lgz_jcl(raw, file_name=JCL_DISPLAY)
    print(f"解析: {len(data.rounds)} 轮传功, 团灭={data.wipe.is_wipe} ({data.wipe.wipe_count}人)")
    for r in data.rounds:
        placer = r.weapon_placer.name if r.weapon_placer else "—"
        print(f"  第{r.round_index}轮 {r.start_rel}~{r.end_rel} 放武器={placer} {r.effect_triggered}")

    # 模拟 ack 文案
    ack = f"收到 {JCL_DISPLAY}，准备进行柳公子传功与团灭分析……"
    print("ACK:", ack)

    await ScreenshotGenerator.launch()
    try:
        result = await LGZAnalyze(JCL_DISPLAY[4:], url, anonymous=False, user_id=0)
        if isinstance(result, str):
            print("FAIL:", result)
            sys.exit(1)
        seg = result[-1] if hasattr(result, "__getitem__") else result
        img_ref = seg.data.get("file") or seg.data.get("url") or ""
        if img_ref.startswith("base64://"):
            import base64
            OUT_IMG.write_bytes(base64.b64decode(img_ref[len("base64://") :]))
            print(f"OK: 图片已保存 {OUT_IMG} ({OUT_IMG.stat().st_size} bytes)")
        elif img_ref and Path(img_ref).exists():
            import shutil
            shutil.copy(img_ref, OUT_IMG)
            print(f"OK: 图片已保存 {OUT_IMG} ({OUT_IMG.stat().st_size} bytes)")
        else:
            print("OK: 分析完成，返回 MessageSegment")
    finally:
        await ScreenshotGenerator.close()
        server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

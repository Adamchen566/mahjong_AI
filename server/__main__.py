"""启动本地麻将服务并打开浏览器。

    python -m server                 # http://127.0.0.1:8000
    python -m server --port 9000 --no-browser
"""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from .app import DEFAULT_DIST, create_app


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m server", description="四川麻将本地服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--delay", type=float, default=0.7, help="电脑每步行动前的停顿(秒)")
    parser.add_argument("--seed", type=int, default=None, help="固定牌局种子(调试用)")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    if not DEFAULT_DIST.is_dir():
        print("提示: 还没有构建界面。先在 frontend/ 里运行 npm install 和 npm run build。")
    print(f"麻将服务已启动: {url}  (Ctrl+C 退出)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(bot_delay=args.delay, seed=args.seed), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

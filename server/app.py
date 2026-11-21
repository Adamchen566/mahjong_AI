"""本地服务: 浏览器通过 WebSocket 和一场 Match 对话。

这是单机软件,同一时间只有一场牌局(保存在 app.state.match)。
刷新页面或重新打开浏览器会接着原来的牌局继续。

浏览器 -> 服务:
    {"type": "new_match", "opponent": "rule" | "simple"}
    {"type": "action", "id": 12}                 执行一个动作
    {"type": "actions", "ids": [88, 89, 90]}     连续执行(换三张一次提交三张)
    {"type": "next_game"}                        开下一局
    {"type": "quit_match"}                       结束整场,回到开始页

服务 -> 浏览器:
    {"type": "state", "match": {...}, "view": {...} | null, "events": [...]}
    {"type": "error", "message": "..."}
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ai import AGENT_LABELS
from chuanma import IllegalAction

from .match import Match, list_records, load_record, record_steps, record_view

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIST = ROOT / "frontend" / "dist"
DEFAULT_RECORDS = ROOT / "records"
PLAYABLE_OPPONENTS = ("rule", "simple")

NOT_BUILT_PAGE = """<!doctype html><meta charset="utf-8"><title>麻将</title>
<body style="font-family: sans-serif; padding: 3rem; line-height: 1.8">
<h2>界面还没有构建</h2>
<p>服务已经在运行,但找不到 <code>frontend/dist</code>。在项目目录里运行一次:</p>
<pre>cd frontend
npm install
npm run build</pre>
<p>然后刷新这个页面。</p>
</body>"""


def create_app(
    records_dir: Optional[Path] = DEFAULT_RECORDS,
    dist_dir: Path = DEFAULT_DIST,
    bot_delay: float = 0.7,
    seed: Optional[int] = None,
) -> FastAPI:
    app = FastAPI(title="chuanma")
    app.state.match = None
    app.state.lock = asyncio.Lock()

    # ------------------------------------------------------------------ HTTP

    @app.get("/api/opponents")
    def opponents() -> Any:
        return [{"id": k, "label": AGENT_LABELS[k]} for k in PLAYABLE_OPPONENTS]

    @app.get("/api/records")
    def records() -> Any:
        return list_records(records_dir) if records_dir else []

    @app.get("/api/records/{name}")
    def record_detail(name: str) -> Any:
        rec = _load(name)
        return {"name": name, "meta": rec.meta, "scores": rec.scores, "steps": record_steps(rec)}

    @app.get("/api/records/{name}/view/{step}")
    def record_at(name: str, step: int) -> Any:
        rec = _load(name)
        return {"step": max(0, min(step, len(rec.actions))), "view": record_view(rec, step)}

    def _load(name: str):
        if records_dir is None:
            raise HTTPException(404, "没有牌谱目录")
        try:
            return load_record(records_dir, name)
        except FileNotFoundError:
            raise HTTPException(404, "找不到这份牌谱") from None

    # ------------------------------------------------------------------ WebSocket

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()

        async def send_state() -> None:
            match: Optional[Match] = app.state.match
            if match is None:
                await websocket.send_json({"type": "state", "match": None, "view": None, "events": []})
            else:
                await websocket.send_json(match.snapshot())

        async def run_bots() -> None:
            """电脑连续行动,直到轮到人或牌局结束。每一步都推给界面,并留出观看的时间。"""
            match: Optional[Match] = app.state.match
            while match is not None and match.bot_to_act:
                if bot_delay and not match.in_setup:
                    await asyncio.sleep(bot_delay)
                match.bot_step()
                await websocket.send_json(match.snapshot())

        async def handle(msg: Dict[str, Any]) -> None:
            kind = msg.get("type")
            match: Optional[Match] = app.state.match
            if kind == "new_match":
                opponent = msg.get("opponent", "rule")
                if opponent not in PLAYABLE_OPPONENTS:
                    raise ValueError(f"未知的对手类型: {opponent}")
                match = Match(opponent=opponent, seed=seed, records_dir=records_dir)
                app.state.match = match
                match.start_game()
            elif kind == "quit_match":
                app.state.match = None
            elif match is None:
                raise ValueError("还没有开始牌局")
            elif kind == "action":
                match.human_action(msg["id"])
            elif kind == "actions":
                for action_id in msg["ids"]:
                    match.human_action(action_id)
            elif kind == "next_game":
                match.start_game()
            else:
                raise ValueError(f"未知的消息类型: {kind}")

        try:
            async with app.state.lock:
                await send_state()
                await run_bots()
            while True:
                msg = await websocket.receive_json()
                async with app.state.lock:
                    try:
                        await handle(msg)
                    except (ValueError, KeyError, TypeError, RuntimeError, IllegalAction) as exc:
                        await websocket.send_json({"type": "error", "message": str(exc)})
                    await send_state()
                    await run_bots()
        except WebSocketDisconnect:
            return

    # ------------------------------------------------------------------ 静态页面

    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        def not_built() -> str:
            return NOT_BUILT_PAGE

    return app

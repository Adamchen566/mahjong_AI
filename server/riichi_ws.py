"""日麻的 WebSocket: /ws/riichi。和川麻的 /ws 是两套,各自保留一场牌局。

浏览器 -> 服务:
    {"type": "new_match", "opponent": "shanten" | "simple"}
    {"type": "action", "id": 12}       执行一个动作(编号见 docs/riichi-rules.md 第 8 节)
    {"type": "continue"}               看完一局的结算,继续下一局
    {"type": "quit_match"}             结束整场,回到开始页

服务 -> 浏览器:
    {"type": "state", "match": {...} | null, "view": {...} | null, "events": [...]}
    {"type": "error", "message": "..."}
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from riichi import IllegalAction

from .riichi_match import OPPONENTS, RiichiMatch


def register_riichi(app: FastAPI, records_dir: Optional[Path], bot_delay: float, seed: Optional[int]) -> None:
    app.state.riichi = None
    riichi_records = records_dir / "riichi" if records_dir else None

    @app.get("/api/riichi/opponents")
    def riichi_opponents() -> Any:
        return [{"id": k, "label": v} for k, v in OPPONENTS.items()]

    @app.websocket("/ws/riichi")
    async def ws_riichi(websocket: WebSocket) -> None:
        await websocket.accept()

        async def send_state() -> None:
            match: Optional[RiichiMatch] = app.state.riichi
            if match is None:
                await websocket.send_json({"type": "state", "match": None, "view": None, "events": []})
            else:
                await websocket.send_json(match.snapshot())

        async def run_bots() -> None:
            match: Optional[RiichiMatch] = app.state.riichi
            while match is not None and match.bot_to_act:
                if bot_delay:
                    await asyncio.sleep(bot_delay)
                match.bot_step()
                await websocket.send_json(match.snapshot())

        def handle(msg: Dict[str, Any]) -> None:
            kind = msg.get("type")
            match: Optional[RiichiMatch] = app.state.riichi
            if kind == "new_match":
                app.state.riichi = RiichiMatch(
                    opponent=msg.get("opponent", "shanten"), seed=seed, records_dir=riichi_records
                )
            elif kind == "quit_match":
                app.state.riichi = None
            elif match is None:
                raise ValueError("还没有开始牌局")
            elif kind == "action":
                match.human_action(msg["id"])
            elif kind == "continue":
                match.resume()
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
                        handle(msg)
                    except (ValueError, KeyError, TypeError, IllegalAction) as exc:
                        await websocket.send_json({"type": "error", "message": str(exc)})
                    await send_state()
                    await run_bots()
        except WebSocketDisconnect:
            return

"""日麻的 WebSocket: /ws/riichi。和川麻的 /ws 是两套,各自保留一场牌局。

浏览器 -> 服务:
    {"type": "new_match", "opponent": "shanten" | "simple"}
    {"type": "action", "id": 12}       执行一个动作(编号见 docs/riichi-rules.md 第 8 节)
    {"type": "continue"}               看完一局的结算,继续下一局
    {"type": "hint", "on": true}       打开或关掉模型提示(打牌建议、点炮概率,需要有模型)
    {"type": "quit_match"}             结束整场,回到开始页

服务 -> 浏览器:
    {"type": "state", "match": {...} | null, "view": {...} | null, "events": [...]}
    {"type": "error", "message": "..."}
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from riichi import IllegalAction

from .riichi_match import OPPONENTS, RiichiMatch, load_advisor
from .riichi_records import list_records, load_record, record_analysis, record_steps, record_view, spectate_record

WATCH_KEEP = 20
SPECTATE_AGENTS = ("shanten", "simple", "net")


def net_ready():
    """日麻模型能不能用: (能不能, 不能的原因)。"""
    try:
        from riichi_ai.onnx_agent import model_status
    except ImportError:
        return False, "没有安装 numpy"
    return model_status()


def register_riichi(
    app: FastAPI, records_dir: Optional[Path], bot_delay: float, seed: Optional[int], advisor: Any = "auto"
) -> None:
    """advisor: 日麻模型;默认自动加载 models/riichi.onnx,没有就没有提示和分析。"""
    app.state.riichi = None
    app.state.riichi_advisor = load_advisor() if advisor == "auto" else advisor
    app.state.riichi_analysis = {}
    riichi_records = records_dir / "riichi" if records_dir else None

    app.state.riichi_watch = OrderedDict()  # 观战的牌谱,只在内存里
    app.state.riichi_watch_no = 0

    @app.get("/api/riichi/opponents")
    def riichi_opponents() -> Any:
        ok, reason = net_ready()
        return [
            {"id": k, "label": v, "available": ok if k == "net" else True, "reason": reason if k == "net" else ""}
            for k, v in OPPONENTS.items()
        ]

    @app.get("/api/riichi/records/{name}/analysis")
    def riichi_record_analysis(name: str) -> Any:
        if app.state.riichi_advisor is None:
            return {"available": False, "reason": net_ready()[1] or "没有可用的模型"}
        rec = _load(name)
        if name not in app.state.riichi_analysis:
            app.state.riichi_analysis[name] = record_analysis(rec, app.state.riichi_advisor)
        return {"available": True, **app.state.riichi_analysis[name]}

    def _load(name: str):
        if name in app.state.riichi_watch:
            return app.state.riichi_watch[name]
        if riichi_records is None:
            raise HTTPException(404, "没有牌谱目录")
        try:
            return load_record(riichi_records, name)
        except FileNotFoundError:
            raise HTTPException(404, "找不到这份牌谱") from None

    @app.get("/api/riichi/records")
    def riichi_record_list() -> Any:
        return list_records(riichi_records) if riichi_records else []

    @app.get("/api/riichi/records/{name}")
    def riichi_record_detail(name: str) -> Any:
        rec = _load(name)
        return {"name": name, "meta": rec.meta, "scores": rec.scores, **record_steps(rec)}

    @app.get("/api/riichi/records/{name}/view/{step}")
    def riichi_record_at(name: str, step: int, seat: Optional[int] = None) -> Any:
        rec = _load(name)
        return {"step": max(0, min(step, len(rec.actions))), "view": record_view(rec, step, seat)}

    @app.post("/api/riichi/spectate")
    def riichi_spectate(body: Dict[str, Any] = Body(...)) -> Any:
        """四个电脑打一场半庄。agents 是东南西北四个座位各用哪种电脑。"""
        agents = body.get("agents")
        if not isinstance(agents, list) or len(agents) != 4 or any(a not in SPECTATE_AGENTS for a in agents):
            raise HTTPException(400, "agents 要给出四个座位各用哪种电脑")
        if "net" in agents:
            ok, reason = net_ready()
            if not ok:
                raise HTTPException(400, f"神经网络现在用不了: {reason}")
        record = spectate_record(agents, seed=body.get("seed", seed))
        app.state.riichi_watch_no += 1
        name = f"rwatch-{app.state.riichi_watch_no}.json"
        app.state.riichi_watch[name] = record
        while len(app.state.riichi_watch) > WATCH_KEEP:
            app.state.riichi_watch.popitem(last=False)
        return {"name": name, "steps": len(record.actions), "agents": agents}

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
                    opponent=msg.get("opponent", "shanten"),
                    seed=seed,
                    records_dir=riichi_records,
                    advisor=app.state.riichi_advisor,
                )
            elif kind == "quit_match":
                app.state.riichi = None
            elif match is None:
                raise ValueError("还没有开始牌局")
            elif kind == "action":
                match.human_action(msg["id"])
            elif kind == "continue":
                match.resume()
            elif kind == "hint":
                if match.advisor is None:
                    raise ValueError("没有可用的模型,开不了提示")
                match.hint_on = bool(msg.get("on"))
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

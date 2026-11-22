"""本地服务: 浏览器通过 WebSocket 和一场 Match 对话。

这是单机软件,同一时间只有一场牌局(保存在 app.state.match)。
刷新页面或重新打开浏览器会接着原来的牌局继续。

浏览器 -> 服务:
    {"type": "new_match", "opponent": "rule" | "simple" | "net"}
    {"type": "hint", "on": true}                 打开或关掉出牌提示(需要有模型)
    {"type": "action", "id": 12}                 执行一个动作
    {"type": "actions", "ids": [88, 89, 90]}     连续执行(换三张一次提交三张)
    {"type": "next_game"}                        开下一局
    {"type": "quit_match"}                       结束整场,回到开始页

服务 -> 浏览器:
    {"type": "state", "match": {...}, "view": {...} | null, "events": [...]}
    {"type": "error", "message": "..."}

观战(四个电脑对打)不走 WebSocket: POST /api/spectate 让服务端把一局打完,
返回一个牌谱名,界面用回放的那一套接口按自己的速度播放。观战的牌谱只放在内存里。
"""
from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ai import AGENT_LABELS
from chuanma import IllegalAction

from .match import (
    Match,
    list_records,
    load_advisor,
    load_record,
    net_status,
    record_analysis,
    record_steps,
    record_view,
    spectate_record,
)
from .riichi_ws import register_riichi

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIST = ROOT / "frontend" / "dist"
DEFAULT_RECORDS = ROOT / "records"
DEFAULT_LADDER = ROOT / "models" / "ladder.json"
PLAYABLE_OPPONENTS = ("simple", "rule", "net")
WATCH_KEEP = 20  # 内存里最多留几局观战的牌谱
_AUTO = object()

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
    advisor: Any = _AUTO,
    ladder_path: Path = DEFAULT_LADDER,
) -> FastAPI:
    """advisor: 提示和复盘分析用的模型。默认自动加载 models/chuanma.onnx,没有就没有这两个功能。"""
    app = FastAPI(title="chuanma")
    app.state.match = None
    app.state.advisor = load_advisor() if advisor is _AUTO else advisor
    app.state.analysis = {}  # 牌谱名 -> 分析结果,算过的不再算
    app.state.watch = OrderedDict()  # 观战的牌谱: 名字 -> GameRecord,只在内存里
    app.state.watch_no = 0
    app.state.lock = asyncio.Lock()

    # ------------------------------------------------------------------ HTTP

    @app.get("/api/opponents")
    def opponents() -> Any:
        ok, reason = net_status()
        return [
            {"id": k, "label": AGENT_LABELS[k], "available": ok if k == "net" else True, "reason": reason if k == "net" else ""}
            for k in PLAYABLE_OPPONENTS
        ]

    @app.get("/api/records")
    def records() -> Any:
        return list_records(records_dir) if records_dir else []

    @app.get("/api/records/{name}")
    def record_detail(name: str) -> Any:
        rec = _load(name)
        return {"name": name, "meta": rec.meta, "scores": rec.scores, "steps": record_steps(rec)}

    @app.get("/api/records/{name}/view/{step}")
    def record_at(name: str, step: int, seat: Optional[int] = None) -> Any:
        rec = _load(name)
        return {"step": max(0, min(step, len(rec.actions))), "view": record_view(rec, step, seat)}

    @app.get("/api/records/{name}/analysis")
    def record_ai_analysis(name: str) -> Any:
        if app.state.advisor is None:
            return {"available": False, "reason": net_status()[1] or "没有可用的模型"}
        rec = _load(name)
        if name not in app.state.analysis:
            app.state.analysis[name] = record_analysis(rec, app.state.advisor)
        return {"available": True, **app.state.analysis[name]}

    @app.post("/api/spectate")
    def spectate(body: Dict[str, Any] = Body(...)) -> Any:
        """四个电脑打一局。agents 是东南西北四个座位各用哪种电脑。"""
        agents = body.get("agents")
        if not isinstance(agents, list) or len(agents) != 4 or any(a not in PLAYABLE_OPPONENTS for a in agents):
            raise HTTPException(400, "agents 要给出四个座位各用哪种电脑")
        if "net" in agents and not net_status()[0]:
            raise HTTPException(400, f"神经网络现在用不了: {net_status()[1]}")
        record = spectate_record(agents, seed=body.get("seed", seed))
        app.state.watch_no += 1
        name = f"watch-{app.state.watch_no}.json"
        app.state.watch[name] = record
        while len(app.state.watch) > WATCH_KEEP:
            old, _ = app.state.watch.popitem(last=False)
            app.state.analysis.pop(old, None)
        return {"name": name, "steps": len(record.actions), "agents": agents}

    @app.get("/api/ladder")
    def ladder() -> Any:
        """段位梯: 各个版本两两对打的成绩和训练曲线,由 python -m ai.ladder 生成。"""
        if not ladder_path.is_file():
            return {"available": False, "reason": "还没有生成段位梯的数据"}
        return {"available": True, **json.loads(ladder_path.read_text(encoding="utf-8"))}

    def _load(name: str):
        if name in app.state.watch:
            return app.state.watch[name]
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
                if opponent == "net" and not net_status()[0]:
                    raise ValueError(f"神经网络对手现在用不了: {net_status()[1]}")
                match = Match(opponent=opponent, seed=seed, records_dir=records_dir, advisor=app.state.advisor)
                app.state.match = match
                match.start_game()
            elif kind == "quit_match":
                app.state.match = None
            elif match is None:
                raise ValueError("还没有开始牌局")
            elif kind == "hint":
                if match.advisor is None:
                    raise ValueError("没有可用的模型,开不了提示")
                match.hint_on = bool(msg.get("on"))
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

    # 日麻: /ws/riichi 和 /api/riichi/*,和上面的川麻互不影响
    register_riichi(app, records_dir, bot_delay, seed)

    # ------------------------------------------------------------------ 静态页面

    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        def not_built() -> str:
            return NOT_BUILT_PAGE

    return app

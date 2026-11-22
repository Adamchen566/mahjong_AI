"""日麻牌谱: 列表、每一步、走到某一步的局面(四家明牌)、观战、模型的复盘分析。

和川麻的 server/match.py 里那几个函数对应,两边互不依赖。牌谱存在 records/riichi/。
"""
from __future__ import annotations

import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from riichi import Action, ActionType, GameRecord, replay
from riichi.game import NUM_SEATS, Game
from riichi.shanten import shanten

from riichi_ai import AGENT_LABELS, make_agent

SEAT_NAMES = ("东", "南", "西", "北")
ROUND_NAMES = ("东", "南", "西", "北")
RECORD_NAME = re.compile(r"^[A-Za-z0-9_\-]+\.json$")


def hand_label(game: Game) -> str:
    return f"{ROUND_NAMES[game.round_wind % 4]}{game.kyoku + 1}局" + (f" {game.honba}本场" if game.honba else "")


def list_records(records_dir: Path) -> List[Dict[str, Any]]:
    out = []
    if not records_dir.is_dir():
        return out
    for path in sorted(records_dir.glob("*.json"), reverse=True):
        try:
            rec = GameRecord.load(path)
        except (ValueError, KeyError, OSError):
            continue
        out.append(
            {
                "name": path.name,
                "saved_at": rec.meta.get("saved_at"),
                "opponent": AGENT_LABELS.get(rec.meta.get("opponent"), rec.meta.get("opponent")),
                "human_seat": rec.meta.get("human_seat", 0),
                "steps": len(rec.actions),
                "scores": rec.scores,
            }
        )
    return out


def load_record(records_dir: Path, name: str) -> GameRecord:
    if not RECORD_NAME.match(name):
        raise FileNotFoundError(name)
    path = records_dir / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return GameRecord.load(path)


def record_steps(record: GameRecord) -> Dict[str, Any]:
    """每一步谁做了什么,以及每一局从第几步开始(界面用它"跳到第几局")。"""
    game = replay(record, upto=0, record_events=False)
    steps = []
    hands = [{"label": hand_label(game), "start": 0}]
    seen = 0
    for action_id in record.actions:
        seat = game.current
        action = Action.from_id(action_id)
        steps.append(
            {
                "seat": seat,
                "text": f"{SEAT_NAMES[seat]} {action}",
                "type": action.type.name,
                "tile": action.tile,
                "hand": len(hands) - 1,
            }
        )
        game.step(action)
        if len(game.hand_results) > seen:
            seen = len(game.hand_results)
            steps[-1]["result"] = game.hand_results[-1]
            if not game.is_over:
                hands.append({"label": hand_label(game), "start": len(steps)})
    return {"steps": steps, "hands": hands}


def record_view(record: GameRecord, step: int, seat: Optional[int] = None) -> Dict[str, Any]:
    """牌谱走到第 step 步之后的局面,四家的牌全部公开。seat 是坐在下方的那一家。"""
    step = max(0, min(step, len(record.actions)))
    game = replay(record, upto=step, record_events=False)
    if seat is None or not 0 <= seat < NUM_SEATS:
        seat = record.meta.get("human_seat", 0)
    view = game.observation(seat)
    view["hands"] = [game.hand_tiles(s) for s in range(NUM_SEATS)]
    view["shanten"] = [shanten(game.hands[s], len(game.melds[s])) for s in range(NUM_SEATS)]
    view["legal"] = []
    view["legal_actions"] = []
    if record.meta.get("agents"):
        view["seat_labels"] = [AGENT_LABELS.get(a, a) for a in record.meta["agents"]]
    if game.is_over:
        view["final"] = {k: v for k, v in game.result().items() if k != "hand_results"}
    return view


def spectate_record(agents: Sequence[str], seed: Optional[int] = None) -> GameRecord:
    """四个电脑打完一场半庄,返回牌谱。"""
    if len(agents) != NUM_SEATS:
        raise ValueError("观战需要四个座位各选一个电脑")
    if seed is None:
        seed = random.randrange(1 << 30)
    players = [make_agent(name, seed + s) for s, name in enumerate(agents)]
    game = Game(seed=seed, record_events=False)
    while not game.is_over:
        s = game.current
        legal = game.legal_actions()
        game.step(legal[0] if len(legal) == 1 else players[s].act(game.observation(s), legal))
    meta = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "spectate": True,
        "agents": list(agents),
        "human_seat": 0,
    }
    return GameRecord.from_game(game, meta=meta)


def record_analysis(record: GameRecord, advisor: Any) -> Dict[str, Any]:
    """把牌谱从头走一遍,每个决策点问模型"你会怎么走",和实际走的对比。模型看的是当时那个座位自己的视图。"""
    game = replay(record, upto=0, record_events=False)
    steps: List[Dict[str, Any]] = []
    decisions = [0] * NUM_SEATS
    agreed = [0] * NUM_SEATS
    for action_id in record.actions:
        seat = game.current
        legal = game.legal_actions()
        if len(legal) == 1:
            steps.append({"seat": seat, "forced": True})
            game.step(action_id)
            continue
        probs, value, _ = advisor.evaluate(game.observation(seat), legal)  # 第三项是点炮概率,分析里不用
        best = max(range(len(legal)), key=probs.__getitem__)
        chosen = next(i for i, a in enumerate(legal) if a.id == action_id)
        decisions[seat] += 1
        agreed[seat] += best == chosen
        ranked = sorted(zip(probs, legal), key=lambda x: -x[0])[:3]
        steps.append(
            {
                "seat": seat,
                "forced": False,
                "value": round(value, 2),
                "agree": best == chosen,
                "chosen": {"id": legal[chosen].id, "text": str(legal[chosen]), "prob": round(probs[chosen], 4)},
                "top": [{"id": a.id, "text": str(a), "prob": round(p, 4)} for p, a in ranked],
                "tiles": tile_probs(probs, legal),
            }
        )
        game.step(action_id)
    return {
        "steps": steps,
        "summary": [{"seat": s, "decisions": decisions[s], "agreed": agreed[s]} for s in range(NUM_SEATS)],
    }


def tile_probs(probs: Sequence[float], legal: Sequence[Action]) -> List[List[float]]:
    """模型对"打出哪张"的看法: [[牌, 概率], ...](同一种牌的赤和普通分开)。"""
    return [[a.tile, round(p, 4)] for p, a in zip(probs, legal) if a.type == ActionType.DISCARD]




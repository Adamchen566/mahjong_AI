"""一场牌局: 1 个人 + 3 个电脑,连打多局,累计积分。

Match 不涉及网络,只管"轮到谁、电脑走一步、人走一步、把人能看到的东西打包"。
网络层(app.py)和测试都直接用它。
"""
from __future__ import annotations

import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai import AGENT_LABELS, make_agent
from chuanma import Action, Game, GameRecord, RuleConfig, replay
from chuanma.game import NUM_SEATS, Phase
from chuanma.tiles import counts_to_tiles

SEAT_NAMES = ("东", "南", "西", "北")
RECORD_NAME = re.compile(r"^[A-Za-z0-9_\-]+\.json$")


class Match:
    def __init__(
        self,
        opponent: str = "rule",
        seed: Optional[int] = None,
        human_seat: int = 0,
        config: Optional[RuleConfig] = None,
        records_dir: Optional[Path] = None,
    ) -> None:
        self.opponent = opponent
        self.human_seat = human_seat
        self.config = config or RuleConfig()
        self.records_dir = records_dir
        self.base_seed = seed if seed is not None else random.randrange(1 << 30)
        self.agents = {
            s: make_agent(opponent, self.base_seed + s) for s in range(NUM_SEATS) if s != human_seat
        }
        self.totals: List[int] = [0] * NUM_SEATS
        self.game_no = 0
        self.game: Optional[Game] = None
        self.last_record: Optional[str] = None
        self._cursor = 0  # 已经发给界面的事件数
        self._finalized = False

    # ------------------------------------------------------------------ 推进

    def start_game(self) -> None:
        """开下一局。庄家按局轮换,种子由整场的种子加局数得到。"""
        if self.game is not None and not self.game.is_over:
            raise RuntimeError("上一局还没打完")
        dealer = self.game_no % NUM_SEATS
        self.game_no += 1
        self.game = Game(config=self.config, seed=self.base_seed + self.game_no, dealer=dealer)
        self.last_record = None
        self._cursor = 0
        self._finalized = False

    @property
    def waiting_for_human(self) -> bool:
        g = self.game
        return g is not None and not g.is_over and g.current == self.human_seat

    @property
    def bot_to_act(self) -> bool:
        g = self.game
        return g is not None and not g.is_over and g.current != self.human_seat

    @property
    def in_setup(self) -> bool:
        """换三张、定缺阶段: 电脑的动作没什么可看的,界面不需要等。"""
        g = self.game
        return g is not None and g.phase in (Phase.EXCHANGE, Phase.CHOOSE_VOID)

    def bot_step(self) -> bool:
        """让当前该行动的电脑走一步。没有电脑要行动时返回 False。"""
        if not self.bot_to_act:
            return False
        g = self.game
        assert g is not None
        seat = g.current
        g.step(self.agents[seat].act(g.observation(seat), g.legal_actions()))
        self._after_step()
        return True

    def human_action(self, action_id: int) -> None:
        if not self.waiting_for_human:
            raise ValueError("现在没有轮到你")
        assert self.game is not None
        self.game.step(Action.from_id(int(action_id)))  # 非法动作会抛 IllegalAction
        self._after_step()

    def _after_step(self) -> None:
        g = self.game
        assert g is not None
        if g.is_over and not self._finalized:
            self._finalized = True
            for s in range(NUM_SEATS):
                self.totals[s] += g.scores[s]
            self._save_record()

    def _save_record(self) -> None:
        if self.records_dir is None:
            return
        g = self.game
        assert g is not None
        self.records_dir.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now():%Y%m%d-%H%M%S}_g{self.game_no}.json"
        meta = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "game_no": self.game_no,
            "opponent": self.opponent,
            "human_seat": self.human_seat,
        }
        GameRecord.from_game(g, meta=meta).save(self.records_dir / name)
        self.last_record = name

    # ------------------------------------------------------------------ 给界面的数据

    def snapshot(self) -> Dict[str, Any]:
        """人这个座位现在能看到的一切,外加自上次以来的新事件。"""
        g = self.game
        data: Dict[str, Any] = {"type": "state", "match": self._match_info(), "view": None, "events": []}
        if g is None:
            return data
        view = g.observation(self.human_seat)
        view["legal"] = (
            [_action_json(a) for a in g.legal_actions()] if self.waiting_for_human else []
        )
        if g.is_over:
            view["transfers"] = [_transfer_json(t) for t in g.transfers]
            view["record"] = self.last_record
        data["view"] = view
        data["events"] = g.events_for(self.human_seat, start=self._cursor)
        self._cursor = len(g.events)
        return data

    def _match_info(self) -> Dict[str, Any]:
        return {
            "game_no": self.game_no,
            "totals": list(self.totals),
            "opponent": self.opponent,
            "opponent_label": AGENT_LABELS.get(self.opponent, self.opponent),
            "human_seat": self.human_seat,
            "seat_names": list(SEAT_NAMES),
        }


# ---------------------------------------------------------------------- 牌谱回放


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
                "game_no": rec.meta.get("game_no"),
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


def record_steps(record: GameRecord) -> List[Dict[str, Any]]:
    """牌谱里每一步是谁做了什么(文字)。"""
    game = replay(record, upto=0, record_events=False)
    steps = []
    for action_id in record.actions:
        seat = game.current
        action = Action.from_id(action_id)
        steps.append({"seat": seat, "text": f"{SEAT_NAMES[seat]} {action}"})
        game.step(action)
    return steps


def record_view(record: GameRecord, step: int) -> Dict[str, Any]:
    """牌谱走到第 step 步之后的局面,四家的牌全部公开。"""
    step = max(0, min(step, len(record.actions)))
    game = replay(record, upto=step, record_events=False)
    seat = record.meta.get("human_seat", 0)
    view = game.observation(seat)
    view["hands"] = [counts_to_tiles(h) for h in game.hands]
    view["melds"] = [
        [{"type": m.type.name, "tile": m.tile, "from_seat": m.from_seat} for m in game.melds[s]]
        for s in range(NUM_SEATS)
    ]
    view["void"] = [v if v >= 0 else None for v in game.void]
    view["legal_actions"] = []
    view["legal"] = []
    view["transfers"] = [_transfer_json(t) for t in game.transfers]
    return view


def _action_json(a: Action) -> Dict[str, Any]:
    return {"id": a.id, "type": a.type.name, "tile": a.tile}


def _transfer_json(t: Any) -> Dict[str, Any]:
    return {"kind": t.kind, "payer": t.payer, "payee": t.payee, "amount": t.amount, "note": t.note}

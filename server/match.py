"""一场牌局: 1 个人 + 3 个电脑,连打多局,累计积分。

Match 不涉及网络,只管"轮到谁、电脑走一步、人走一步、把人能看到的东西打包"。
网络层(app.py)和测试都直接用它。
"""
from __future__ import annotations

import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ai import AGENT_LABELS, make_agent
from chuanma import Action, Game, GameRecord, RuleConfig, replay
from chuanma.game import NUM_SEATS, Phase
from chuanma.tiles import counts_to_tiles

SEAT_NAMES = ("东", "南", "西", "北")
RECORD_NAME = re.compile(r"^[A-Za-z0-9_\-]+\.json$")


def net_status() -> Tuple[bool, str]:
    """训练出的模型能不能用,以及不能用的原因。"""
    try:
        from ai.onnx_agent import model_status
    except ImportError:
        return False, "没有安装 numpy"
    return model_status()


def load_advisor() -> Optional[Any]:
    """提示和复盘分析用的模型。没有模型文件或缺依赖时返回 None,软件照常能玩。"""
    if not net_status()[0]:
        return None
    from ai.onnx_agent import OnnxAgent

    return OnnxAgent()


def advise(advisor: Any, obs: Dict[str, Any], legal: List[Action], top: int = 3) -> Dict[str, Any]:
    """模型对这个局面的看法: 概率最高的几个动作,和它估计这一局还会得多少分。

    obs 必须是某个座位自己的 observation(),所以建议里不可能用到别人的手牌。
    """
    probs, value = advisor.evaluate(obs, legal)
    ranked = sorted(zip(probs, legal), key=lambda x: -x[0])[:top]
    return {
        "value": round(value, 2),
        "choices": [{**_action_json(a), "prob": round(p, 4), "text": str(a)} for p, a in ranked],
    }


class Match:
    def __init__(
        self,
        opponent: str = "rule",
        seed: Optional[int] = None,
        human_seat: int = 0,
        config: Optional[RuleConfig] = None,
        records_dir: Optional[Path] = None,
        advisor: Optional[Any] = None,
    ) -> None:
        self.advisor = advisor  # 给提示用的模型;None 表示没有
        self.hint_on = False
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
        if self.hint_on and self.advisor is not None and self.waiting_for_human:
            view["hint"] = advise(self.advisor, g.observation(self.human_seat), g.legal_actions())
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
            "hint_available": self.advisor is not None,
            "hint_on": self.hint_on and self.advisor is not None,
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


def record_analysis(record: GameRecord, advisor: Any) -> Dict[str, Any]:
    """把牌谱从头走一遍,每个决策点问模型"你会怎么走",和实际走的对比。

    模型看到的是当时那个座位自己的视图,不是事后摊开的牌。
    steps[i] 对应牌谱的第 i+1 步。只有一个选择的步骤标 forced,不参与统计。
    """
    game = replay(record, upto=0, record_events=False)
    steps: List[Dict[str, Any]] = []
    decisions = [0] * NUM_SEATS
    agreed = [0] * NUM_SEATS
    for action_id in record.actions:
        seat = game.current
        legal = game.legal_actions()
        if len(legal) == 1:
            steps.append({"seat": seat, "forced": True})
        else:
            probs, value = advisor.evaluate(game.observation(seat), legal)
            best = max(range(len(legal)), key=probs.__getitem__)
            chosen = next(i for i, a in enumerate(legal) if a.id == action_id)
            decisions[seat] += 1
            agreed[seat] += best == chosen
            steps.append(
                {
                    "seat": seat,
                    "forced": False,
                    "agree": best == chosen,
                    "best": {**_action_json(legal[best]), "prob": round(probs[best], 4), "text": str(legal[best])},
                    "chosen": {**_action_json(legal[chosen]), "prob": round(probs[chosen], 4), "text": str(legal[chosen])},
                    "value": round(value, 2),
                }
            )
        game.step(action_id)
    return {
        "steps": steps,
        "summary": [{"seat": s, "decisions": decisions[s], "agreed": agreed[s]} for s in range(NUM_SEATS)],
    }


def _action_json(a: Action) -> Dict[str, Any]:
    return {"id": a.id, "type": a.type.name, "tile": a.tile}


def _transfer_json(t: Any) -> Dict[str, Any]:
    return {"kind": t.kind, "payer": t.payer, "payee": t.payee, "amount": t.amount, "note": t.note}

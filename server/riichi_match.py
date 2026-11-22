"""日麻的一场牌局: 1 个人 + 3 个电脑打一整场半庄。

和川麻的 Match 是两套,互不影响。引擎的 Game 本身就是一整场,一局打完会自动开下一局;
这里在每局结束时暂停,等人看完结算点"下一局"(continue)再往下走。
"""
from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from riichi import Action, ActionType, Game, GameRecord, make_agent
from riichi.game import NUM_SEATS
from riichi.shanten import discard_shanten, shanten, useful_tiles
from riichi.tiles import FIVE_KINDS, kind_of

OPPONENTS = {"shanten": "规则型", "simple": "简单"}
SEAT_NAMES = ("东", "南", "西", "北")


def action_json(game: Game, a: Action) -> Dict[str, Any]:
    """一个合法动作给界面的样子。吃碰另外给出从手里拿出去的两张牌。"""
    out: Dict[str, Any] = {"id": a.id, "type": a.type.name, "tile": a.tile, "text": str(a)}
    if a.type in (ActionType.CHI, ActionType.PON) and game.pending is not None:
        k = kind_of(game.pending[1])
        if a.type == ActionType.PON:
            kinds = [k, k]
            red = bool(a.arg)
        else:
            shape, red_i = divmod(a.arg, 2)
            kinds = list(((k + 1, k + 2), (k - 1, k + 1), (k - 2, k - 1))[shape])
            red = bool(red_i)
        uses = []
        for j in kinds:
            if red and j in FIVE_KINDS and not any(u >= 34 for u in uses):
                uses.append(34 + j // 9)
            else:
                uses.append(j)
        out["uses"] = uses
    return out


def insight(view: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """牌理: 只用这个座位自己的视图算向听数、进张、听哪些牌。"""
    if view["phase"] not in ("TURN", "RIICHI", "RESPONSE", "ROB_KAN"):
        return None
    seat = view["seat"]
    counts = [0] * 34
    for t in view["hand"]:
        counts[kind_of(t)] += 1
    melds = len(view["melds"][seat])
    seen = list(counts)
    for ms in view["melds"]:
        for m in ms:
            for t in m["tiles"]:
                seen[kind_of(t)] += 1
    for d, flags in zip(view["discards"], view["discard_flags"]):
        for t, f in zip(d, flags):
            if not f[2]:
                seen[kind_of(t)] += 1
    for t in view["dora_indicators"]:
        seen[kind_of(t)] += 1

    def info(c: List[int]) -> Dict[str, Any]:
        sh = shanten(c, melds)
        useful = useful_tiles(c, melds)
        items = [{"tile": k, "left": max(0, 4 - seen[k])} for k in useful]
        return {"shanten": sh, "tiles": items, "total": sum(i["left"] for i in items)}

    if sum(counts) % 3 == 1:
        return info(counts)
    per = discard_shanten(counts, melds)
    best = min(per.values())
    options = {}
    for k, sh in per.items():
        if sh == best:
            counts[k] -= 1
            options[k] = info(counts)
            counts[k] += 1
    top = max(o["total"] for o in options.values())
    for o in options.values():
        o["best"] = o["total"] == top
    return {"shanten": best, "discards": options}


class RiichiMatch:
    def __init__(
        self,
        opponent: str = "shanten",
        seed: Optional[int] = None,
        human_seat: int = 0,
        records_dir: Optional[Path] = None,
    ) -> None:
        if opponent not in OPPONENTS:
            raise ValueError(f"未知的对手类型: {opponent}")
        self.opponent = opponent
        self.human_seat = human_seat
        self.records_dir = records_dir
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.agents = {s: make_agent(opponent, self.seed + s) for s in range(NUM_SEATS) if s != human_seat}
        self.game = Game(seed=self.seed)
        self.paused = False  # 一局刚结束,等人看完结算
        self.last_record: Optional[str] = None
        self._cursor = 0
        self._hands_seen = 0

    # ------------------------------------------------------------------ 推进

    @property
    def waiting_for_human(self) -> bool:
        g = self.game
        return not self.paused and not g.is_over and g.current == self.human_seat

    @property
    def bot_to_act(self) -> bool:
        g = self.game
        return not self.paused and not g.is_over and g.current != self.human_seat

    def bot_step(self) -> bool:
        if not self.bot_to_act:
            return False
        g = self.game
        seat = g.current
        g.step(self.agents[seat].act(g.observation(seat), g.legal_actions()))
        self._after_step()
        return True

    def human_action(self, action_id: int) -> None:
        if not self.waiting_for_human:
            raise ValueError("现在没有轮到你")
        self.game.step(Action.from_id(int(action_id)))  # 非法动作会抛 IllegalAction
        self._after_step()

    def resume(self) -> None:
        """看完一局的结算,继续下一局。"""
        if self.game.is_over:
            raise ValueError("这一场已经结束了")
        self.paused = False

    def _after_step(self) -> None:
        g = self.game
        if len(g.hand_results) > self._hands_seen:
            self._hands_seen = len(g.hand_results)
            self.paused = True
        if g.is_over and self.last_record is None:
            self._save_record()

    def _save_record(self) -> None:
        if self.records_dir is None:
            return
        self.records_dir.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now():%Y%m%d-%H%M%S}_riichi.json"
        meta = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "opponent": self.opponent,
            "human_seat": self.human_seat,
        }
        GameRecord.from_game(self.game, meta=meta).save(self.records_dir / name)
        self.last_record = name

    # ------------------------------------------------------------------ 给界面的数据

    def snapshot(self) -> Dict[str, Any]:
        g = self.game
        view = g.observation(self.human_seat)
        view["legal"] = [action_json(g, a) for a in g.legal_actions()] if self.waiting_for_human else []
        if not self.paused and not g.is_over:
            tips = insight(view)
            if tips is not None:
                view["insight"] = tips
        if self.paused or g.is_over:
            view["result"] = g.hand_results[-1] if g.hand_results else None
        if g.is_over:
            view["final"] = {k: v for k, v in g.result().items() if k != "hand_results"}
            view["record"] = self.last_record
        events = g.events_for(self.human_seat)
        data = {
            "type": "state",
            "match": {
                "opponent": self.opponent,
                "opponent_label": OPPONENTS[self.opponent],
                "human_seat": self.human_seat,
                "paused": self.paused,
                "over": g.is_over,
            },
            "view": view,
            "events": events[self._cursor :],
        }
        self._cursor = len(events)
        return data

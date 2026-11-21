"""规则型 AI(阶段 4a): 向听数 + 有效进张。

它只用自己座位的 observation,不看别人的手牌。决策原则:

    出牌   打掉后向听数最小;相同时,有效进张的剩余张数最多;
           已经听牌时,比较"能胡的剩余张数 × 胡牌得分"
    碰     只有让向听数变小才碰
    杠     不让向听数变大就杠
    胡     能胡就胡
    定缺   缺哪门之后向听数最小就缺哪门
    换三张 换出去之后剩下的牌向听数最小
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from chuanma.actions import Action, ActionType
from chuanma.agents import keep_value, suit_size
from chuanma.config import RuleConfig
from chuanma.fan import Meld, MeldType, WinContext, evaluate_fan
from chuanma.hand import winning_tiles
from chuanma.shanten import shanten, useful_tiles
from chuanma.tiles import COPIES, NUM_RANKS, NUM_SUITS, tiles_to_counts

_RON = WinContext(zimo=False)
_GANG_TYPES = ("MING_GANG", "AN_GANG", "JIA_GANG")


class RuleAgent:
    def __init__(self, seed: Optional[int] = None, config: Optional[RuleConfig] = None) -> None:
        # seed 只是为了和其他策略保持同样的构造方式;这个策略是确定性的
        self.config = config or RuleConfig()

    # ------------------------------------------------------------------ 入口

    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action:
        by_type: Dict[ActionType, List[Action]] = {}
        for a in legal:
            by_type.setdefault(a.type, []).append(a)

        if ActionType.HU in by_type:
            return by_type[ActionType.HU][0]
        if ActionType.EXCHANGE in by_type:
            return self._exchange(obs, by_type[ActionType.EXCHANGE])
        if ActionType.CHOOSE_VOID in by_type:
            return self._choose_void(obs, by_type[ActionType.CHOOSE_VOID])

        ctx = _Context(obs)
        if ActionType.DISCARD in by_type:
            gang = self._self_gang(ctx, by_type)
            if gang is not None:
                return gang
            return self._discard(ctx, by_type[ActionType.DISCARD])
        return self._respond(ctx, by_type)

    # ------------------------------------------------------------------ 换三张 / 定缺

    def _exchange(self, obs: Dict[str, Any], options: List[Action]) -> Action:
        given = list(obs["exchange"]["given"])
        full = tiles_to_counts(list(obs["hand"]) + given)  # 还原成选牌之前的手牌
        plan = _exchange_plan(full)
        for t in given:
            if t not in plan:
                # 前面选的牌不在自己的方案里(生成训练数据时会故意随机走几步):
                # 花色已经定了,就在这门里挑剩下最没用的一张
                counts = tiles_to_counts(obs["hand"])
                return min(options, key=lambda a: (keep_value(counts, a.tile), a.tile))
            plan.remove(t)
        return Action(ActionType.EXCHANGE, plan[0])

    def _choose_void(self, obs: Dict[str, Any], options: List[Action]) -> Action:
        counts = tiles_to_counts(obs["hand"])
        return min(
            options,
            key=lambda a: (shanten(counts, 0, a.tile), suit_size(counts, a.tile), a.tile),
        )

    # ------------------------------------------------------------------ 自己的回合

    def _self_gang(self, ctx: "_Context", by_type: Dict[ActionType, List[Action]]) -> Optional[Action]:
        gangs = by_type.get(ActionType.AN_GANG, []) + by_type.get(ActionType.JIA_GANG, [])
        if not gangs:
            return None
        counts = ctx.counts
        now = min(
            _shanten_without(counts, a.tile, 1, ctx.num_melds, ctx.void)
            for a in by_type[ActionType.DISCARD]
        )
        for a in gangs:
            if a.type == ActionType.AN_GANG:
                after = _shanten_without(counts, a.tile, COPIES, ctx.num_melds + 1, ctx.void)
            else:  # 加杠: 碰已经算作一组副露
                after = _shanten_without(counts, a.tile, 1, ctx.num_melds, ctx.void)
            if after <= now:
                return a
        return None

    def _discard(self, ctx: "_Context", options: List[Action]) -> Action:
        counts = ctx.counts
        void = ctx.void
        tiles = sorted({a.tile for a in options})
        if all(t // NUM_RANKS == void for t in tiles):
            # 被迫打缺门: 打哪张对牌型都没影响,挑最安全的
            best = min(tiles, key=lambda t: (ctx.danger(t), t))
            return Action(ActionType.DISCARD, best)

        scored: List[Tuple[int, int]] = []
        for t in tiles:
            scored.append((_shanten_without(counts, t, 1, ctx.num_melds, void), t))
        best_shanten = min(s for s, _ in scored)
        candidates = [t for s, t in scored if s == best_shanten]

        def rank(t: int) -> Tuple[float, int, int, int]:
            counts[t] -= 1
            try:
                if best_shanten == 0:
                    value = self._tenpai_value(ctx)
                else:
                    value = sum(ctx.remaining[u] for u in useful_tiles(counts, ctx.num_melds, void))
            finally:
                counts[t] += 1
            return (-value, ctx.danger(t), keep_value(counts, t), t)

        return Action(ActionType.DISCARD, min(candidates, key=rank))

    def _tenpai_value(self, ctx: "_Context") -> float:
        """听牌时的期望价值: 每种能胡的牌 剩余张数 × 胡牌得分 之和。"""
        counts = ctx.counts
        waits = winning_tiles(counts, ctx.num_melds, ctx.void, ctx.meld_tiles)
        value = 0.0
        for w in waits:
            if not ctx.remaining[w]:
                continue
            counts[w] += 1
            points = evaluate_fan(counts, ctx.melds, _RON, self.config).points
            counts[w] -= 1
            value += ctx.remaining[w] * points
        return value

    # ------------------------------------------------------------------ 响应别人的牌

    def _respond(self, ctx: "_Context", by_type: Dict[ActionType, List[Action]]) -> Action:
        tile = ctx.obs["pending_discard"]["tile"]
        counts = ctx.counts
        now = shanten(counts, ctx.num_melds, ctx.void)
        if ActionType.MING_GANG in by_type:
            if _shanten_without(counts, tile, 3, ctx.num_melds + 1, ctx.void) <= now:
                return by_type[ActionType.MING_GANG][0]
        if ActionType.PONG in by_type:
            # 碰后是 14 张型,向听数已经包含了"再打掉一张"
            if _shanten_without(counts, tile, 2, ctx.num_melds + 1, ctx.void) < now:
                return by_type[ActionType.PONG][0]
        return by_type[ActionType.PASS][0]


class _Context:
    """从 observation 里整理出决策要用的量。"""

    def __init__(self, obs: Dict[str, Any]) -> None:
        self.obs = obs
        seat = obs["seat"]
        self.seat = seat
        self.counts = tiles_to_counts(obs["hand"])
        void = obs["void"][seat]
        self.void = -1 if void is None else void

        self.melds: List[Meld] = [
            Meld(MeldType[m["type"]], m["tile"], m["from_seat"]) for m in obs["melds"][seat]
        ]
        self.num_melds = len(self.melds)
        self.meld_tiles = [m.tile for m in self.melds for _ in range(m.size)]

        # 自己能看到的每种牌的张数 -> 还可能摸到的张数
        seen = list(self.counts)
        for row in obs["melds"]:
            for m in row:
                if m["tile"] is not None:
                    seen[m["tile"]] += 4 if m["type"] in _GANG_TYPES else 3
        for pile in obs["discards"]:
            for t in pile:
                seen[t] += 1
        self.seen = seen
        self.remaining = [max(0, COPIES - n) for n in seen]

        # 还在牌局里的对手各自缺哪门: 缺某门的人不可能胡那门的牌
        self.opponent_voids = [
            obs["void"][s] for s in range(4) if s != seat and not obs["won"][s]
        ]

    def danger(self, tile: int) -> int:
        """打出这张牌的危险程度: 能胡它的对手越多越危险,场上见得越多越安全。"""
        suit = tile // NUM_RANKS
        threats = sum(1 for v in self.opponent_voids if v != suit)
        return threats * 10 - self.seen[tile]


def _shanten_without(counts: List[int], tile: int, n: int, num_melds: int, void: int) -> int:
    counts[tile] -= n
    try:
        return shanten(counts, num_melds, void)
    finally:
        counts[tile] += n


def _exchange_plan(counts: List[int]) -> List[int]:
    """决定换出哪三张: 每门花色各试一次,取换出后向听数最小的方案。"""
    best_key = None
    best_picks: List[int] = []
    for suit in range(NUM_SUITS):
        size = suit_size(counts, suit)
        if size < 3:
            continue
        c = list(counts)
        picks: List[int] = []
        for _ in range(3):
            options = [t for t in range(suit * NUM_RANKS, (suit + 1) * NUM_RANKS) if c[t]]
            t = min(options, key=lambda x: (keep_value(c, x), x))
            c[t] -= 1
            picks.append(t)
        after = min(shanten(c, 0, v) for v in range(NUM_SUITS))
        key = (after, size, suit)
        if best_key is None or key < best_key:
            best_key, best_picks = key, picks
    return best_picks


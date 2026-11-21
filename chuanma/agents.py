"""策略接口和两个基础策略。

策略只拿到自己座位的 observation(看不到别人的手牌)和合法动作列表,返回其中一个动作。
人、规则型 AI、神经网络都实现同一个接口。
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Protocol

from .actions import Action, ActionType
from .tiles import NUM_RANKS, tiles_to_counts


class Agent(Protocol):
    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action: ...


class RandomAgent:
    """从合法动作里随机选。用于压力测试。"""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.rng = random.Random(seed)

    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action:
        return self.rng.choice(legal)


class SimpleAgent:
    """简单的规则型策略: 能胡就胡、能杠就杠、能碰就碰,出牌时丢最孤立的牌。

    它只是引擎自带的陪练和测试对手。真正的规则型 AI(向听数 + 有效进张)在阶段 4a 实现。
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self.rng = random.Random(seed)

    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action:
        by_type: Dict[ActionType, List[Action]] = {}
        for a in legal:
            by_type.setdefault(a.type, []).append(a)

        for kind in (ActionType.HU, ActionType.AN_GANG, ActionType.JIA_GANG, ActionType.MING_GANG, ActionType.PONG):
            if kind in by_type:
                return by_type[kind][0]

        counts = tiles_to_counts(obs["hand"])
        if ActionType.CHOOSE_VOID in by_type:
            # 缺张数最少的一门
            return min(by_type[ActionType.CHOOSE_VOID], key=lambda a: (suit_size(counts, a.tile), a.tile))
        if ActionType.EXCHANGE in by_type:
            options = by_type[ActionType.EXCHANGE]
            given = obs["exchange"]["given"]
            if not given:
                # 第一张决定花色: 选张数最少(但够三张)的那门
                suit = min({a.tile // NUM_RANKS for a in options}, key=lambda s: (suit_size(counts, s), s))
                options = [a for a in options if a.tile // NUM_RANKS == suit]
            return min(options, key=lambda a: (keep_value(counts, a.tile), a.tile))
        if ActionType.DISCARD in by_type:
            return min(by_type[ActionType.DISCARD], key=lambda a: (keep_value(counts, a.tile), a.tile))
        return by_type[ActionType.PASS][0]


def suit_size(counts: List[int], suit: int) -> int:
    return sum(counts[suit * NUM_RANKS : (suit + 1) * NUM_RANKS])


def keep_value(counts: List[int], tile: int) -> int:
    """一张牌留在手里的价值: 成对/成刻、有邻张的牌更值得留。"""
    suit, idx = divmod(tile, NUM_RANKS)
    base = suit * NUM_RANKS
    value = (counts[tile] - 1) * 6
    for offset, weight in ((-1, 3), (1, 3), (-2, 1), (2, 1)):
        j = idx + offset
        if 0 <= j < NUM_RANKS and counts[base + j]:
            value += weight
    if idx in (0, NUM_RANKS - 1):
        value -= 1  # 幺九牌搭子少
    return value


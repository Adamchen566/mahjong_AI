"""策略接口和三个规则型策略。

策略只拿到自己座位的 observation 和合法动作列表,返回其中一个。

| 策略 | 行为 | 用途 |
|---|---|---|
| RandomAgent | 随机选 | 压力测试 |
| SimpleAgent | 能和就和,不吃碰,丢最孤立的牌 | 陪练、测试 |
| ShantenAgent | 向听数 + 有效进张;听牌就立直;只碰役牌;别人立直时没听就弃和 | 模仿学习的老师、强度标尺 |
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Protocol, Sequence

from .actions import Action, ActionType
from .shanten import discard_shanten, shanten, useful_tiles
from .tiles import NUM_KINDS, YAOCHU_SET, dora_of, kind_of, tiles_to_counts


class Agent(Protocol):
    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action: ...


def _by_type(legal: Sequence[Action]) -> Dict[ActionType, List[Action]]:
    out: Dict[ActionType, List[Action]] = {}
    for a in legal:
        out.setdefault(a.type, []).append(a)
    return out


class RandomAgent:
    """从合法动作里随机选。"""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.rng = random.Random(seed)

    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action:
        return self.rng.choice(legal)


def keep_value(counts: Sequence[int], k: int) -> int:
    """一张牌留在手里的价值: 成对、有邻张的更值得留;字牌孤张最没用。"""
    value = (counts[k] - 1) * 6
    if k < 27:
        base = k - k % 9
        idx = k % 9
        for off, w in ((-1, 3), (1, 3), (-2, 1), (2, 1)):
            j = idx + off
            if 0 <= j < 9 and counts[base + j]:
                value += w
        if idx in (0, 8):
            value -= 1
    else:
        value -= 2
    return value


class SimpleAgent:
    """能和就和,九种九牌就流局,不吃碰杠不立直,丢最孤立的牌。"""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.rng = random.Random(seed)

    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action:
        by = _by_type(legal)
        for t in (ActionType.TSUMO, ActionType.RON):
            if t in by:
                return by[t][0]
        if ActionType.PASS in by:
            return by[ActionType.PASS][0]
        counts = tiles_to_counts(obs["hand"])
        return min(by[ActionType.DISCARD], key=lambda a: (keep_value(counts, kind_of(a.arg)), a.arg < 34, a.arg))


def _visible(obs: Dict[str, Any]) -> List[int]:
    """这个座位已经看到的每种牌的张数(手牌、所有副露、所有弃牌、宝牌指示牌)。"""
    seen = tiles_to_counts(obs["hand"])
    for ms in obs["melds"]:
        for m in ms:
            for t in m["tiles"]:
                seen[kind_of(t)] += 1
    for seat, d in enumerate(obs["discards"]):
        flags = obs["discard_flags"][seat]
        for t, f in zip(d, flags):
            if not f[2]:  # 被吃碰走的已经算在副露里
                seen[kind_of(t)] += 1
    for t in obs["dora_indicators"]:
        seen[kind_of(t)] += 1
    return seen


class ShantenAgent:
    """向听数 + 有效进张的规则型策略。

    | 场合 | 做法 |
    |---|---|
    | 出牌 | 让向听数最小;同向听时有效进张(扣掉看得见的)最多;再比牌的价值,宝牌和赤牌尽量留 |
    | 和牌 | 能和就和 |
    | 立直 | 门清听牌就立直(打出后进张最多的那张) |
    | 吃碰 | 只碰役牌(三元牌、自风、场风);已经副露了才吃碰能减少向听的牌 |
    | 杠 | 暗杠、加杠在不增加向听时就杠;大明杠不杠 |
    | 防守 | 别人立直而自己两向听以上:打现物,没有现物打字牌和幺九 |
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self.rng = random.Random(seed)

    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action:
        by = _by_type(legal)
        for t in (ActionType.TSUMO, ActionType.RON):
            if t in by:
                return by[t][0]
        counts = tiles_to_counts(obs["hand"])
        seat = obs["seat"]
        n_melds = len(obs["melds"][seat])
        if ActionType.KYUUSHU in by:
            if sum(1 for k in YAOCHU_SET if counts[k]) < 11:
                return by[ActionType.KYUUSHU][0]
        if obs["phase"] in ("RESPONSE", "ROB_KAN"):
            return self._respond(obs, by, counts, n_melds)
        if obs["phase"] == "RIICHI":
            return self._best_discard(obs, by[ActionType.DISCARD], counts, n_melds)
        for t in (ActionType.ANKAN, ActionType.KAKAN):
            for a in by.get(t, []):
                c = list(counts)
                c[a.arg] = 0 if t == ActionType.ANKAN else c[a.arg] - 1
                extra = 1 if t == ActionType.ANKAN else 0
                if shanten(c, n_melds + extra) <= shanten(counts, n_melds):
                    return a
        if ActionType.RIICHI in by:
            return by[ActionType.RIICHI][0]
        if ActionType.DISCARD in by:
            return self._best_discard(obs, by[ActionType.DISCARD], counts, n_melds)
        return legal[0]

    def _respond(self, obs, by, counts, n_melds) -> Action:
        pass_ = by[ActionType.PASS][0]
        pending = obs["pending"]
        if pending is None:
            return pass_
        k = kind_of(pending["tile"])
        seat = obs["seat"]
        yakuhai = {31, 32, 33, 27 + obs["seat_wind"], 27 + obs["round_wind"] % 4}
        if any(r for i, r in enumerate(obs["riichi"]) if i != seat):
            return pass_
        before = shanten(counts, n_melds)
        options = []
        for a in by.get(ActionType.PON, []):
            if k in yakuhai or n_melds > 0:
                c = list(counts)
                c[k] -= 2
                options.append((self._best_after_call(c, n_melds + 1), a))
        if n_melds > 0:
            for a in by.get(ActionType.CHI, []):
                shape = a.arg // 2
                pair = ((k + 1, k + 2), (k - 1, k + 1), (k - 2, k - 1))[shape]
                c = list(counts)
                for j in pair:
                    c[j] -= 1
                options.append((self._best_after_call(c, n_melds + 1), a))
        if not options:
            return pass_
        best_sh, best = min(options, key=lambda x: (x[0], x[1].id))
        return best if best_sh < before else pass_

    @staticmethod
    def _best_after_call(c: List[int], melds: int) -> int:
        best = 99
        for j in range(NUM_KINDS):
            if c[j]:
                c[j] -= 1
                best = min(best, shanten(c, melds))
                c[j] += 1
        return best

    def _best_discard(self, obs, options: List[Action], counts, n_melds) -> Action:
        seat = obs["seat"]
        threat = [i for i, r in enumerate(obs["riichi"]) if r and i != seat]
        seen = _visible(obs)
        dora = {dora_of(kind_of(t)) for t in obs["dora_indicators"]}
        # 先算每种候选牌打出后的向听数,只给向听最小的那些算进张
        sh_of = discard_shanten(counts, n_melds)
        min_sh = min(sh_of[kind_of(a.arg)] for a in options)
        cache: Dict[int, tuple] = {}

        def evaluate(k: int) -> tuple:
            if k not in cache:
                sh = sh_of[k]
                ukeire = 0
                if sh == min_sh and sh <= 3:
                    c = list(counts)
                    c[k] -= 1
                    ukeire = sum(max(0, 4 - seen[u]) for u in useful_tiles(c, n_melds))
                cache[k] = (sh, -ukeire)
            return cache[k]

        current = shanten(counts, n_melds)
        if threat and current >= 2:
            safe = set()
            for i in threat:
                safe |= {kind_of(t) for t in obs["discards"][i]}

            def danger(a: Action) -> tuple:
                k = kind_of(a.arg)
                if k in safe:
                    return (0, evaluate(k))
                return (1 if k >= 27 else 2 if k in YAOCHU_SET else 3, evaluate(k))

            return min(options, key=lambda a: (danger(a), a.arg >= 34, a.arg))

        def score(a: Action) -> tuple:
            k = kind_of(a.arg)
            return (
                evaluate(k),
                1 if (k in dora or a.arg >= 34) else 0,
                keep_value(counts, k),
                a.arg,
            )

        return min(options, key=score)


AGENTS = {"random": RandomAgent, "simple": SimpleAgent, "shanten": ShantenAgent}


def make_agent(name: str, seed: Optional[int] = None) -> Agent:
    return AGENTS[name](seed)

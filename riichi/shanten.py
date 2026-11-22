"""向听数: 一手牌离听牌还差几张有用的牌。

    -1 = 已经和了    0 = 听牌    1 = 一向听 ...

标准型、七对子、国士无双分别算,取最小的。引擎本身的规则判定不依赖这个模块
(听牌用 hand.waits 判断),它是给规则型策略和牌理提示用的。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from .tiles import NUM_KINDS, YAOCHU

_YAOCHU_SET = frozenset(YAOCHU)

SuitOptions = Tuple[Tuple[int, int, int], ...]  # (面子数, 是否含雀头, 搭子数)


@lru_cache(maxsize=None)
def _suit_options(c: Tuple[int, ...]) -> SuitOptions:
    """枚举一门数牌能拆出的 (面子数, 雀头, 搭子数),每个 (面子数, 雀头) 只留搭子最多的。"""
    best = {}
    counts = list(c)

    def rec(i: int, melds: int, pair: int, partials: int) -> None:
        while i < 9 and counts[i] == 0:
            i += 1
        if i == 9:
            key = (melds, pair)
            if partials > best.get(key, -1):
                best[key] = partials
            return
        n = counts[i]
        if n >= 3:
            counts[i] -= 3
            rec(i, melds + 1, pair, partials)
            counts[i] += 3
        if i <= 6 and counts[i + 1] and counts[i + 2]:
            counts[i] -= 1
            counts[i + 1] -= 1
            counts[i + 2] -= 1
            rec(i, melds + 1, pair, partials)
            counts[i] += 1
            counts[i + 1] += 1
            counts[i + 2] += 1
        if n >= 2:
            counts[i] -= 2
            if not pair:
                rec(i, melds, 1, partials)
            rec(i, melds, pair, partials + 1)
            counts[i] += 2
        if i <= 7 and counts[i + 1]:
            counts[i] -= 1
            counts[i + 1] -= 1
            rec(i, melds, pair, partials + 1)
            counts[i] += 1
            counts[i + 1] += 1
        if i <= 6 and counts[i + 2]:
            counts[i] -= 1
            counts[i + 2] -= 1
            rec(i, melds, pair, partials + 1)
            counts[i] += 1
            counts[i + 2] += 1
        counts[i] -= 1
        rec(i, melds, pair, partials)
        counts[i] += 1

    rec(0, 0, 0, 0)
    return tuple((m, p, t) for (m, p), t in best.items())


@lru_cache(maxsize=None)
def _honor_options(c: Tuple[int, ...]) -> SuitOptions:
    melds = sum(1 for n in c if n >= 3)
    pairs = sum(1 for n in c if n == 2)
    if pairs:
        return ((melds, 0, pairs), (melds, 1, pairs - 1))
    return ((melds, 0, 0),)


@lru_cache(maxsize=None)
def _options(g: int, seg: Tuple[int, ...]) -> SuitOptions:
    return _suit_options(seg) if g < 3 else _honor_options(seg)


def _combine(states: dict, options: SuitOptions, need: int) -> dict:
    """把一门牌的拆法并进状态。

    状态: (面子数, 有没有雀头) -> 最多的搭子数。面子数封顶 need,搭子数封顶 need - 面子数;
    向听数只取决于封顶后的值,而且搭子越多越好,所以每个键只留最大的,状态最多 2*(need+1) 个。
    """
    merged: dict = {}
    for (m0, p0), t0 in states.items():
        for m1, p1, t1 in options:
            p = p0 + p1
            if p > 1:
                continue
            m = m0 + m1
            if m > need:
                m = need
            t = t0 + t1
            if t > need - m:
                t = need - m
            key = (m, p)
            if t > merged.get(key, -1):
                merged[key] = t
    return merged


def _value(states: dict, need: int) -> int:
    best = 2 * need
    for (m, p), t in states.items():
        v = 2 * need - 2 * m - t - p
        if v < best:
            best = v
    return best


def _seven(counts: Sequence[int]) -> int:
    kinds = 0
    pairs = 0
    for n in counts:
        if n:
            kinds += 1
            if n >= 2:
                pairs += 1
    return 6 - pairs + max(0, 7 - kinds)


def _kokushi(counts: Sequence[int]) -> int:
    have = 0
    pair = 0
    for k in YAOCHU:
        if counts[k]:
            have += 1
            if counts[k] >= 2:
                pair = 1
    return 13 - have - pair


def _segments(counts: Sequence[int]) -> List[Tuple[int, ...]]:
    return [tuple(counts[g * 9 : g * 9 + 9]) for g in range(4)]


@lru_cache(maxsize=500_000)
def _shanten_cached(counts: Tuple[int, ...], num_melds: int) -> int:
    need = 4 - num_melds
    states = {(0, 0): 0}
    for g, seg in enumerate(_segments(counts)):
        if any(seg):
            states = _combine(states, _options(g, seg), need)
    best = _value(states, need)
    if num_melds == 0:
        best = min(best, _seven(counts), _kokushi(counts))
    return best


def shanten(counts: Sequence[int], num_melds: int = 0) -> int:
    """向听数。counts 是手里的牌(不含副露),13 张型或 14 张型都可以。"""
    return _shanten_cached(tuple(counts), num_melds)


@lru_cache(maxsize=1_000_000)
def _rest_value(rest: Tuple[Tuple[Tuple[int, int], int], ...], g: int, seg: Tuple[int, ...], need: int) -> int:
    return _value(_combine(dict(rest), _options(g, seg), need), need)


class _OneSuitChange:
    """只改动一张牌时快速重算向听数。

    标准型: 其余三门的组合先算好复用,只重算改动的那一门。
    七对子、国士: 加减一张牌时向听数最多变 1,用增量公式。
    """

    def __init__(self, counts: Sequence[int], num_melds: int) -> None:
        self.counts = counts
        self.num_melds = num_melds
        self.need = 4 - num_melds
        self.segs = _segments(counts)
        self.rest: List[Optional[tuple]] = [None] * 4
        if num_melds == 0:
            self.kinds = sum(1 for n in counts if n)
            self.pairs = sum(1 for n in counts if n >= 2)
            self.have = sum(1 for k in YAOCHU if counts[k])
            self.yaochu_pair = any(counts[k] >= 2 for k in YAOCHU)

    def _special(self, k: int, delta: int) -> int:
        n = self.counts[k]
        kinds, pairs = self.kinds, self.pairs
        have, ypair = self.have, self.yaochu_pair
        if delta > 0:
            if n == 0:
                kinds += 1
            elif n == 1:
                pairs += 1
        else:
            if n == 1:
                kinds -= 1
            elif n == 2:
                pairs -= 1
        seven = 6 - pairs + max(0, 7 - kinds)
        if k in _YAOCHU_SET:
            if delta > 0:
                if n == 0:
                    have += 1
                elif n == 1:
                    ypair = True
            else:
                if n == 1:
                    have -= 1
                elif n == 2:
                    ypair = any(self.counts[j] >= 2 for j in YAOCHU if j != k)
        kokushi = 13 - have - (1 if ypair else 0)
        return min(seven, kokushi)

    def shanten_with(self, k: int, delta: int) -> int:
        g = k // 9 if k < 27 else 3
        i = k - g * 9
        rest = self.rest[g]
        if rest is None:
            states = {(0, 0): 0}
            for h, seg in enumerate(self.segs):
                if h != g and any(seg):
                    states = _combine(states, _options(h, seg), self.need)
            rest = self.rest[g] = tuple(sorted(states.items()))
        seg = self.segs[g]
        best = _rest_value(rest, g, seg[:i] + (seg[i] + delta,) + seg[i + 1 :], self.need)
        if self.num_melds == 0:
            special = self._special(k, delta)
            if special < best:
                best = special
        return best


def useful_tiles(counts: Sequence[int], num_melds: int = 0) -> List[int]:
    """有效进张: 摸到哪些种类的牌能让向听数减少。counts 应为 13 张型。"""
    base = _shanten_cached(tuple(counts), num_melds)
    change = _OneSuitChange(counts, num_melds)
    c = counts
    out: List[int] = []
    kinds = sum(1 for n in c if n)
    for k in range(NUM_KINDS):
        if c[k] >= 4:
            continue
        # 和手里任何牌都不相邻(同门相差 2 以内)的牌对标准型没有用;
        # 只有七对子(种类不够 7 种)或国士(幺九牌)可能用得上
        if not c[k]:
            near = False
            if k < 27:
                lo, hi = k - k % 9, k - k % 9 + 8
                for j in range(max(lo, k - 2), min(hi, k + 2) + 1):
                    if c[j]:
                        near = True
                        break
            if not near and not (num_melds == 0 and (kinds < 7 or k in _YAOCHU_SET)):
                continue
        if change.shanten_with(k, 1) < base:
            out.append(k)
    return out


def discard_shanten(counts: Sequence[int], num_melds: int = 0) -> Dict[int, int]:
    """14 张型: 打出每一种手里有的牌之后的向听数。"""
    change = _OneSuitChange(counts, num_melds)
    return {k: change.shanten_with(k, -1) for k in range(NUM_KINDS) if counts[k]}

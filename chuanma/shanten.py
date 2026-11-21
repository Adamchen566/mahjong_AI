"""向听数: 一手牌离听牌还差几张有用的牌。

    -1 = 已经胡了    0 = 听牌    1 = 一向听(再进一张有用的牌就听) ...

缺门的牌一律当废牌,不参与计算。标准型和七对型分别算,取较小者。
既可以算 13 张型(13 - 3*副露数 张),也可以算 14 张型(刚摸牌、还没出牌)。
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Sequence, Tuple

from .tiles import NUM_RANKS, NUM_SUITS, NUM_TILE_TYPES

# 单门花色的拆解结果: 若干 (面子数, 是否含将, 搭子数),只保留不被别的结果全面压过的
SuitOptions = Tuple[Tuple[int, int, int], ...]


@lru_cache(maxsize=None)
def _suit_options(c: Tuple[int, ...]) -> SuitOptions:
    """枚举单门花色能拆出的 (面子数, 将, 搭子数) 组合。"""
    best = {}  # (面子数, 将) -> 最多搭子数
    counts = list(c)

    def rec(i: int, melds: int, pair: int, partials: int) -> None:
        while i < NUM_RANKS and counts[i] == 0:
            i += 1
        if i == NUM_RANKS:
            key = (melds, pair)
            if partials > best.get(key, -1):
                best[key] = partials
            return
        n = counts[i]
        # 刻子
        if n >= 3:
            counts[i] -= 3
            rec(i, melds + 1, pair, partials)
            counts[i] += 3
        # 顺子
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
                rec(i, melds, 1, partials)  # 作将
            rec(i, melds, pair, partials + 1)  # 作对子搭子
            counts[i] += 2
        # 两面/边张搭子
        if i <= 7 and counts[i + 1]:
            counts[i] -= 1
            counts[i + 1] -= 1
            rec(i, melds, pair, partials + 1)
            counts[i] += 1
            counts[i + 1] += 1
        # 嵌张搭子
        if i <= 6 and counts[i + 2]:
            counts[i] -= 1
            counts[i + 2] -= 1
            rec(i, melds, pair, partials + 1)
            counts[i] += 1
            counts[i + 2] += 1
        # 当作孤张丢掉
        counts[i] -= 1
        rec(i, melds, pair, partials)
        counts[i] += 1

    rec(0, 0, 0, 0)
    return tuple((m, p, t) for (m, p), t in best.items())


@lru_cache(maxsize=200_000)
def _shanten_cached(counts: Tuple[int, ...], num_melds: int, void_suit: int) -> int:
    need = 4 - num_melds  # 还要从手牌里凑出的面子数
    states = {(0, 0, 0)}
    for suit in range(NUM_SUITS):
        if suit == void_suit:
            continue
        seg = counts[suit * NUM_RANKS : (suit + 1) * NUM_RANKS]
        if not any(seg):
            continue
        options = _suit_options(seg)
        merged = set()
        for m0, p0, t0 in states:
            for m1, p1, t1 in options:
                if p0 + p1 <= 1:
                    merged.add((m0 + m1, p0 + p1, t0 + t1))
        states = merged

    best = 2 * need
    for m, p, t in states:
        m = min(m, need)
        t = min(t, need - m)  # 面子 + 搭子 最多 need 组
        value = 2 * need - 2 * m - t - p
        if value < best:
            best = value

    if num_melds == 0:
        pairs = 0
        odd = 0
        for t in range(NUM_TILE_TYPES):
            if t // NUM_RANKS == void_suit:
                continue
            pairs += counts[t] // 2
            odd += counts[t] % 2
        pairs = min(pairs, 7)
        seven = 6 - pairs + max(0, 7 - pairs - odd)
        if seven < best:
            best = seven
    return best


def shanten(counts: Sequence[int], num_melds: int = 0, void_suit: int = -1) -> int:
    """向听数。counts 是手牌计数(不含副露),void_suit 是缺门(-1 表示还没定缺)。"""
    return _shanten_cached(tuple(counts), num_melds, void_suit)


def useful_tiles(counts: Sequence[int], num_melds: int = 0, void_suit: int = -1) -> List[int]:
    """有效进张: 摸到哪些牌能让向听数减少。counts 应为 13 张型。"""
    base = shanten(counts, num_melds, void_suit)
    c = list(counts)
    out: List[int] = []
    for t in range(NUM_TILE_TYPES):
        if t // NUM_RANKS == void_suit or c[t] >= 4:
            continue
        # 离手里任何一张牌都超过两格的牌不可能有用(七对型除外,单独处理)
        c[t] += 1
        if _shanten_cached(tuple(c), num_melds, void_suit) < base:
            out.append(t)
        c[t] -= 1
    return out

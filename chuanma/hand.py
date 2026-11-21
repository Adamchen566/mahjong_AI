"""手牌分析:判胡、拆牌、听牌。全部基于长度 27 的计数列表。"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Sequence, Tuple

from .tiles import NUM_RANKS, NUM_SUITS, NUM_TILE_TYPES

# 一种拆法: (将牌, ((是否刻子, 牌), ...)),顺子用最小的那张牌表示
Decomposition = Tuple[int, Tuple[Tuple[bool, int], ...]]


@lru_cache(maxsize=None)
def _suit_all_melds(c: Tuple[int, ...]) -> bool:
    """单门花色的 9 个计数能否恰好拆成若干面子(顺子/刻子),不留牌。"""
    for i in range(NUM_RANKS):
        if c[i]:
            break
    else:
        return True
    if c[i] >= 3:
        rest = list(c)
        rest[i] -= 3
        if _suit_all_melds(tuple(rest)):
            return True
    if i <= 6 and c[i + 1] and c[i + 2]:
        rest = list(c)
        rest[i] -= 1
        rest[i + 1] -= 1
        rest[i + 2] -= 1
        if _suit_all_melds(tuple(rest)):
            return True
    return False


@lru_cache(maxsize=None)
def _suit_melds_and_pair(c: Tuple[int, ...]) -> bool:
    """单门花色能否拆成 若干面子 + 一对将。"""
    for i in range(NUM_RANKS):
        if c[i] >= 2:
            rest = list(c)
            rest[i] -= 2
            if _suit_all_melds(tuple(rest)):
                return True
    return False


def is_standard_win(counts: Sequence[int]) -> bool:
    """标准胡型: n 个面子 + 1 对将。张数必须是 3n+2,由调用方保证与副露数匹配。"""
    pair_suits = 0
    for s in range(NUM_SUITS):
        seg = tuple(counts[s * NUM_RANKS : (s + 1) * NUM_RANKS])
        rem = sum(seg) % 3
        if rem == 1:
            return False
        if rem == 2:
            pair_suits += 1
            if pair_suits > 1 or not _suit_melds_and_pair(seg):
                return False
        elif not _suit_all_melds(seg):
            return False
    return pair_suits == 1


def is_seven_pairs(counts: Sequence[int]) -> bool:
    """七对: 14 张全在手里,每种牌都是偶数张(4 张算两对)。"""
    return sum(counts) == 14 and all(n % 2 == 0 for n in counts)


def is_win(counts: Sequence[int], num_melds: int) -> bool:
    """手牌(已含要胡的那张)加上 num_melds 组副露,是否构成胡型。不检查缺门。"""
    if sum(counts) != 14 - 3 * num_melds:
        return False
    if num_melds == 0 and is_seven_pairs(counts):
        return True
    return is_standard_win(counts)


def standard_decompositions(counts: Sequence[int]) -> List[Decomposition]:
    """列出标准胡型的所有拆法(可能有重复),不是胡型时返回空列表。"""
    if sum(counts) % 3 != 2:
        return []
    c = list(counts)
    results: List[Decomposition] = []
    for pair in range(NUM_TILE_TYPES):
        if c[pair] >= 2:
            c[pair] -= 2
            _decompose(c, 0, [], results, pair)
            c[pair] += 2
    return results


def _decompose(c: List[int], start: int, acc: list, results: list, pair: int) -> None:
    i = start
    while i < NUM_TILE_TYPES and c[i] == 0:
        i += 1
    if i == NUM_TILE_TYPES:
        results.append((pair, tuple(acc)))
        return
    if c[i] >= 3:
        c[i] -= 3
        acc.append((True, i))
        _decompose(c, i, acc, results, pair)
        acc.pop()
        c[i] += 3
    if i % NUM_RANKS <= 6 and c[i + 1] and c[i + 2]:
        c[i] -= 1
        c[i + 1] -= 1
        c[i + 2] -= 1
        acc.append((False, i))
        _decompose(c, i, acc, results, pair)
        acc.pop()
        c[i] += 1
        c[i + 1] += 1
        c[i + 2] += 1


def has_suit(counts: Sequence[int], suit: int) -> bool:
    """手里是否还有某门花色的牌。"""
    return any(counts[suit * NUM_RANKS : (suit + 1) * NUM_RANKS])


def winning_tiles(
    counts: Sequence[int], num_melds: int, void_suit: int, meld_tiles: Sequence[int] = ()
) -> List[int]:
    """听哪些牌。counts 是未含胡牌张的手牌(13 - 3*副露数 张)。

    meld_tiles 是副露里的全部牌(碰 3 张、杠 4 张,逐张列出)。
    手里还有缺门牌时不算听牌。一种牌自己已经占满 4 张时不算能听它。
    """
    if void_suit >= 0 and has_suit(counts, void_suit):
        return []
    if sum(counts) != 13 - 3 * num_melds:
        return []
    c = list(counts)
    owned = list(counts)
    for t in meld_tiles:
        owned[t] += 1
    waits: List[int] = []
    for t in range(NUM_TILE_TYPES):
        if t // NUM_RANKS == void_suit or owned[t] >= 4:
            continue
        c[t] += 1
        if is_win(c, num_melds):
            waits.append(t)
        c[t] -= 1
    return waits

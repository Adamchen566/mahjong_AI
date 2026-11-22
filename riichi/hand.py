"""和牌型的判定、听牌、拆法。

这里只看"形",不管有没有役。counts 一律是长度 34 的按种类计数,只含手里的牌(不含副露)。
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Sequence, Tuple

from .tiles import NUM_KINDS, YAOCHU

# 一组面子: (0, 顺子最小的那张) 或 (1, 刻子的牌)
Set = Tuple[int, int]
CHI, PON = 0, 1
# 一种拆法: (雀头, 面子列表)
Decomposition = Tuple[int, Tuple[Set, ...]]


@lru_cache(maxsize=None)
def _suit_sets(c: Tuple[int, ...]) -> bool:
    """一门数牌能否正好拆成若干顺子和刻子。"""
    i = 0
    while i < 9 and c[i] == 0:
        i += 1
    if i == 9:
        return True
    if c[i] >= 3:
        if _suit_sets(c[:i] + (c[i] - 3,) + c[i + 1 :]):
            return True
    if i <= 6 and c[i + 1] and c[i + 2]:
        if _suit_sets(c[:i] + (c[i] - 1, c[i + 1] - 1, c[i + 2] - 1) + c[i + 3 :]):
            return True
    return False


@lru_cache(maxsize=None)
def _suit_sets_pair(c: Tuple[int, ...]) -> bool:
    """一门数牌能否拆成 若干面子 + 一对雀头。"""
    for i in range(9):
        if c[i] >= 2 and _suit_sets(c[:i] + (c[i] - 2,) + c[i + 1 :]):
            return True
    return False


def is_standard(counts: Sequence[int]) -> bool:
    """手里的牌能否拆成 若干面子 + 一对雀头(面子数由张数决定)。"""
    pair_group = -1
    for g in range(4):
        n = 0
        for k in range(g * 9, g * 9 + (9 if g < 3 else 7)):
            n += counts[k]
        r = n % 3
        if r == 1:
            return False
        if r == 2:
            if pair_group >= 0:
                return False
            pair_group = g
    if pair_group < 0:
        return False
    for g in range(3):
        seg = tuple(counts[g * 9 : g * 9 + 9])
        if pair_group == g:
            if not _suit_sets_pair(seg):
                return False
        elif not _suit_sets(seg):
            return False
    pairs = 0
    for k in range(27, 34):
        n = counts[k]
        if n == 2:
            pairs += 1
        elif n not in (0, 3):
            return False
    return pairs == (1 if pair_group == 3 else 0)


def is_chiitoi(counts: Sequence[int]) -> bool:
    """七对子: 7 种不同的牌各 2 张。"""
    pairs = 0
    for n in counts:
        if n == 2:
            pairs += 1
        elif n:
            return False
    return pairs == 7


def is_kokushi(counts: Sequence[int]) -> bool:
    """国士无双: 13 种幺九牌各至少 1 张,其中一种 2 张,共 14 张。"""
    total = 0
    for k in YAOCHU:
        if not counts[k]:
            return False
        total += counts[k]
    return total == 14 and sum(counts) == 14


def is_agari(counts: Sequence[int], num_melds: int = 0) -> bool:
    """是不是和牌型。counts 应当有 14 - 3*副露数 张。"""
    if is_standard(counts):
        return True
    return num_melds == 0 and (is_chiitoi(counts) or is_kokushi(counts))


@lru_cache(maxsize=200_000)
def _waits_cached(counts: Tuple[int, ...], num_melds: int) -> Tuple[int, ...]:
    c = list(counts)
    # 候选: 手里有的牌,以及同门相差 2 以内的牌(标准型和七对子听的牌只可能是这些);
    # 国士另外加上全部幺九牌
    cand = [False] * NUM_KINDS
    for k in range(NUM_KINDS):
        if c[k]:
            if k < 27:
                lo = k - k % 9
                for j in range(max(lo, k - 2), min(lo + 8, k + 2) + 1):
                    cand[j] = True
            else:
                cand[k] = True
    if num_melds == 0 and sum(1 for k in YAOCHU if c[k]) >= 12:
        for k in YAOCHU:
            cand[k] = True
    out = []
    for k in range(NUM_KINDS):
        if c[k] >= 4 or not cand[k]:
            continue
        c[k] += 1
        if is_agari(c, num_melds):
            out.append(k)
        c[k] -= 1
    return tuple(out)


def waits(counts: Sequence[int], num_melds: int = 0) -> Tuple[int, ...]:
    """听哪些牌(种类)。counts 应当有 13 - 3*副露数 张。

    只看形:不管还剩几张、有没有役。手里已经有 4 张的牌不算。
    """
    return _waits_cached(tuple(counts), num_melds)


@lru_cache(maxsize=50_000)
def _decompose_cached(counts: Tuple[int, ...]) -> Tuple[Decomposition, ...]:
    out: List[Decomposition] = []
    c = list(counts)

    def rec(i: int, sets: List[Set], pair: int) -> None:
        while i < NUM_KINDS and c[i] == 0:
            i += 1
        if i == NUM_KINDS:
            out.append((pair, tuple(sets)))
            return
        if c[i] >= 3:
            c[i] -= 3
            sets.append((PON, i))
            rec(i, sets, pair)
            sets.pop()
            c[i] += 3
        if i < 27 and i % 9 <= 6 and c[i + 1] and c[i + 2]:
            c[i] -= 1
            c[i + 1] -= 1
            c[i + 2] -= 1
            sets.append((CHI, i))
            rec(i, sets, pair)
            sets.pop()
            c[i] += 1
            c[i + 1] += 1
            c[i + 2] += 1

    for p in range(NUM_KINDS):
        if c[p] >= 2:
            c[p] -= 2
            rec(0, [], p)
            c[p] += 2
    return tuple(out)


def decompose(counts: Sequence[int]) -> Tuple[Decomposition, ...]:
    """列出标准型(面子 + 雀头)的全部拆法;不是标准和牌型时返回空。"""
    return _decompose_cached(tuple(counts))

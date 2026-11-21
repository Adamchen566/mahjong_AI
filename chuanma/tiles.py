"""牌的表示。

四川麻将只有万、筒、条三门,共 27 种牌,每种 4 张,合计 108 张。
引擎内部用 0..26 的整数表示一种牌:

    tile = suit * 9 + (rank - 1)

    suit: 0 = 万(m)  1 = 筒(p)  2 = 条(s)
    rank: 1..9

手牌用长度 27 的计数列表表示(counts[tile] = 张数),判胡和训练都直接用它。
"""
from __future__ import annotations

from typing import Iterable, List

NUM_SUITS = 3
NUM_RANKS = 9
NUM_TILE_TYPES = NUM_SUITS * NUM_RANKS  # 27
COPIES = 4
NUM_TILES = NUM_TILE_TYPES * COPIES  # 108

SUIT_MAN, SUIT_PIN, SUIT_SOU = 0, 1, 2
SUIT_CODES = ("m", "p", "s")
SUIT_NAMES = ("万", "筒", "条")


def make_tile(suit: int, rank: int) -> int:
    if not (0 <= suit < NUM_SUITS and 1 <= rank <= NUM_RANKS):
        raise ValueError(f"非法的牌: suit={suit}, rank={rank}")
    return suit * NUM_RANKS + rank - 1


def suit_of(tile: int) -> int:
    return tile // NUM_RANKS


def rank_of(tile: int) -> int:
    return tile % NUM_RANKS + 1


def tile_str(tile: int) -> str:
    """紧凑写法,例如 5m、9p、1s。"""
    return f"{rank_of(tile)}{SUIT_CODES[suit_of(tile)]}"


def tile_name(tile: int) -> str:
    """中文写法,例如 5万、9筒、1条。"""
    return f"{rank_of(tile)}{SUIT_NAMES[suit_of(tile)]}"


def parse_tile(text: str) -> int:
    """解析单张牌,例如 "5m"。"""
    tiles = parse_tiles(text)
    if len(tiles) != 1:
        raise ValueError(f"应当只有一张牌: {text!r}")
    return tiles[0]


def parse_tiles(text: str) -> List[int]:
    """解析紧凑写法,例如 "123m456p77s" 或 "1m 2m 3m"。空格会被忽略。"""
    tiles: List[int] = []
    ranks: List[int] = []
    for ch in text:
        if ch.isspace():
            continue
        if ch.isdigit():
            ranks.append(int(ch))
        elif ch in SUIT_CODES:
            if not ranks:
                raise ValueError(f"花色 {ch!r} 前面缺少数字: {text!r}")
            suit = SUIT_CODES.index(ch)
            tiles.extend(make_tile(suit, r) for r in ranks)
            ranks = []
        else:
            raise ValueError(f"无法识别的字符 {ch!r}: {text!r}")
    if ranks:
        raise ValueError(f"末尾的数字缺少花色: {text!r}")
    return tiles


def tiles_str(tiles: Iterable[int]) -> str:
    """把一组牌写成紧凑写法(按花色合并),例如 [0,1,2,9] -> "123m1p"。"""
    by_suit: List[List[int]] = [[] for _ in range(NUM_SUITS)]
    for t in sorted(tiles):
        by_suit[suit_of(t)].append(rank_of(t))
    return "".join(
        "".join(map(str, ranks)) + SUIT_CODES[s] for s, ranks in enumerate(by_suit) if ranks
    )


def tiles_to_counts(tiles: Iterable[int]) -> List[int]:
    counts = [0] * NUM_TILE_TYPES
    for t in tiles:
        counts[t] += 1
    return counts


def counts_to_tiles(counts: Iterable[int]) -> List[int]:
    """计数列表 -> 从小到大排好序的牌列表。"""
    tiles: List[int] = []
    for t, n in enumerate(counts):
        if n:
            tiles.extend([t] * n)
    return tiles


def full_wall() -> List[int]:
    """未洗的整副牌(108 张)。"""
    return [t for t in range(NUM_TILE_TYPES) for _ in range(COPIES)]

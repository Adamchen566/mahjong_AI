"""牌的表示。

日本麻将有 34 种牌,每种 4 张,合计 136 张。

种类(kind)用 0..33 的整数:

    万 0..8   筒 9..17   条 18..26   东南西北 27..30   白发中 31..33

具体的一张牌(tile)在种类之外再多三个编号,表示赤 5:

    34 = 赤5万   35 = 赤5筒   36 = 赤5条

赤牌和普通 5 是同一种牌(kind_of 把 34/35/36 折回 4/13/22),只是多算一番宝牌。
手牌用长度 34 的计数列表(按种类)加一个长度 3 的赤牌计数表示。
"""
from __future__ import annotations

from typing import Iterable, List, Sequence

NUM_KINDS = 34
NUM_TILE_CODES = 37  # 34 种 + 3 张赤牌
NUM_TILES = 136

SUIT_CODES = ("m", "p", "s", "z")
SUIT_NAMES = ("万", "筒", "条")
HONOR_NAMES = ("东", "南", "西", "北", "白", "发", "中")
WIND_NAMES = ("东", "南", "西", "北")

EAST, SOUTH, WEST, NORTH, HAKU, HATSU, CHUN = range(27, 34)
RED_MAN, RED_PIN, RED_SOU = 34, 35, 36
RED_TILES = (RED_MAN, RED_PIN, RED_SOU)
FIVE_KINDS = (4, 13, 22)

_KIND_OF = list(range(34)) + [4, 13, 22]

YAOCHU = (0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33)
YAOCHU_SET = frozenset(YAOCHU)
TERMINALS = frozenset((0, 8, 9, 17, 18, 26))
HONORS = frozenset(range(27, 34))
GREENS = frozenset((19, 20, 21, 23, 25, 32))  # 23468 条 + 发


def kind_of(tile: int) -> int:
    """一张牌的种类(赤 5 折回普通 5)。"""
    return _KIND_OF[tile]


def is_red(tile: int) -> bool:
    return tile >= 34


def red_of(kind: int) -> int:
    """这种牌对应的赤牌编号;不是 5 则返回 -1。"""
    if kind == 4:
        return RED_MAN
    if kind == 13:
        return RED_PIN
    if kind == 22:
        return RED_SOU
    return -1


def suit_of(kind: int) -> int:
    """0 万、1 筒、2 条、3 字。"""
    return kind // 9


def rank_of(kind: int) -> int:
    """数牌的点数 1..9;字牌是 1..7。"""
    return kind % 9 + 1


def is_honor(kind: int) -> bool:
    return kind >= 27


def is_yaochu(kind: int) -> bool:
    return kind in YAOCHU_SET


def dora_of(indicator_kind: int) -> int:
    """宝牌指示牌的下一张。"""
    k = indicator_kind
    if k < 27:
        return k - 8 if k % 9 == 8 else k + 1
    if k < 31:
        return 27 + (k - 27 + 1) % 4
    return 31 + (k - 31 + 1) % 3


def tile_str(tile: int) -> str:
    """紧凑写法: 5m、0p(赤 5 筒)、1z(东)。"""
    if tile >= 34:
        return "0" + SUIT_CODES[tile - 34]
    return f"{tile % 9 + 1}{SUIT_CODES[tile // 9]}"


def tile_name(tile: int) -> str:
    """中文写法: 5万、赤5筒、东。"""
    if tile >= 34:
        return "赤5" + SUIT_NAMES[tile - 34]
    if tile >= 27:
        return HONOR_NAMES[tile - 27]
    return f"{tile % 9 + 1}{SUIT_NAMES[tile // 9]}"


def parse_tiles(text: str) -> List[int]:
    """解析紧凑写法,例如 "123m406p77s1122z"。0 表示赤 5;z 是字牌 1..7。"""
    out: List[int] = []
    digits: List[int] = []
    for ch in text:
        if ch.isspace():
            continue
        if ch.isdigit():
            digits.append(int(ch))
        elif ch in SUIT_CODES:
            if not digits:
                raise ValueError(f"花色前没有数字: {text!r}")
            s = SUIT_CODES.index(ch)
            for d in digits:
                if s == 3:
                    if not 1 <= d <= 7:
                        raise ValueError(f"非法的字牌: {d}z")
                    out.append(27 + d - 1)
                elif d == 0:
                    out.append(34 + s)
                else:
                    out.append(s * 9 + d - 1)
            digits = []
        else:
            raise ValueError(f"无法解析: {text!r}")
    if digits:
        raise ValueError(f"末尾缺少花色: {text!r}")
    return out


def parse_tile(text: str) -> int:
    tiles = parse_tiles(text)
    if len(tiles) != 1:
        raise ValueError(f"应当只有一张牌: {text!r}")
    return tiles[0]


def sort_key(tile: int) -> float:
    """排序用: 赤 5 排在普通 5 前面。"""
    return _KIND_OF[tile] - 0.5 if tile >= 34 else tile


def tiles_str(tiles: Iterable[int]) -> str:
    """把一组牌写成紧凑写法(按花色分组、排好序)。"""
    groups: List[List[str]] = [[], [], [], []]
    for t in sorted(tiles, key=sort_key):
        if t >= 34:
            groups[t - 34].append("0")
        else:
            groups[t // 9].append(str(t % 9 + 1))
    return "".join("".join(g) + SUIT_CODES[i] for i, g in enumerate(groups) if g)


def tiles_to_counts(tiles: Iterable[int]) -> List[int]:
    """按种类计数(赤牌算进对应的 5)。"""
    counts = [0] * NUM_KINDS
    for t in tiles:
        counts[_KIND_OF[t]] += 1
    return counts


def count_reds(tiles: Iterable[int]) -> List[int]:
    reds = [0, 0, 0]
    for t in tiles:
        if t >= 34:
            reds[t - 34] += 1
    return reds


def hand_tiles(counts: Sequence[int], reds: Sequence[int]) -> List[int]:
    """把 计数 + 赤牌数 还原成排好序的牌列表。"""
    out: List[int] = []
    for k in range(NUM_KINDS):
        n = counts[k]
        if not n:
            continue
        if k in FIVE_KINDS and reds[k // 9]:
            r = reds[k // 9]
            out.extend([34 + k // 9] * r)
            n -= r
        out.extend([k] * n)
    return out


def full_wall(aka: bool = True) -> List[int]:
    """一副完整的 136 张牌(未洗)。aka 为真时每门的 5 有一张是赤的。"""
    wall: List[int] = []
    for k in range(NUM_KINDS):
        if aka and k in FIVE_KINDS:
            wall.extend([34 + k // 9, k, k, k])
        else:
            wall.extend([k] * 4)
    return wall

# mahjong/tiles.py

from enum import Enum
from dataclasses import dataclass
from typing import List


class Suit(Enum):
    MANZU = "man"    # 万
    PINZU = "pin"    # 饼
    SOUZU = "sou"    # 条
    WIND = "wind"    # 风
    DRAGON = "dragon"  # 三元
    FLOWER = "flower"  # 花牌


class Wind(Enum):
    EAST = "east"
    SOUTH = "south"
    WEST = "west"
    NORTH = "north"


class Dragon(Enum):
    WHITE = "white"
    GREEN = "green"
    RED = "red"


class Flower(Enum):
    PLUM = "plum"
    ORCHID = "orchid"
    BAMBOO = "bamboo"
    CHRYSANTHEMUM = "chrysanthemum"
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"

def tile_sort_key(tile: "Tile") -> int:
    """定义麻将牌排序规则：万 < 饼 < 条 < 风 < 箭 < 花"""
    suit_order = {
        Suit.MANZU: 0,
        Suit.PINZU: 1,
        Suit.SOUZU: 2,
        Suit.WIND: 3,
        Suit.DRAGON: 4,
        Suit.FLOWER: 5
    }

    value_order = 0
    if isinstance(tile.value, int):
        value_order = tile.value
    elif isinstance(tile.value, Enum):
        value_order = list(type(tile.value)).index(tile.value)

    return suit_order[tile.suit] * 100 + value_order

# 增加 __lt__ 用于内置排序函数 sorted(tile_list)
@dataclass(frozen=True)
class Tile:
    suit: Suit
    value: int | Wind | Dragon | Flower

    def __str__(self):
        return f"{self.value}{self.suit.value}" if isinstance(self.value, int) else f"{self.value.name}"

    def __lt__(self, other: "Tile"):
        return tile_sort_key(self) < tile_sort_key(other)
    

def generate_tile_set(set_type: str) -> List[Tile]:
    """
    根据指定的牌组类型生成牌组。
    Args:
        set_type (str): 牌组类型，支持 "chuan"（四川麻将，108张牌）和 "nanjing"（南京麻将，144张牌）。
    Returns:
        List[Tile]: 生成的牌组列表。
    Raises:
        ValueError: 如果输入的牌组类型不是 "chuan" 或 "nanjing"，则抛出异常。
        
    Generate tile sets:
    - "chuan" for Sichuan (108 tiles)
    - "nanjing" for Nanjing (144 tiles)
    """
    tiles: List[Tile] = []

    # 1. 万, 条, 饼：1-9 各四张
    for suit in [Suit.MANZU, Suit.PINZU, Suit.SOUZU]:
        for value in range(1, 10):
            tiles.extend([Tile(suit, value)] * 4)

    if set_type == "nanjing":
        # 2. 东南西北：各四张
        for wind in Wind:
            tiles.extend([Tile(Suit.WIND, wind)] * 4)

        # 3. 红中, 发财, 白板：各四张
        for dragon in Dragon:
            tiles.extend([Tile(Suit.DRAGON, dragon)] * 4)

        # 4. 花牌：每种1张，共8张
        for flower in Flower:
            tiles.append(Tile(Suit.FLOWER, flower))

    return tiles

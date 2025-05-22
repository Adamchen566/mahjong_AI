# mahjong/player.py
from enum import Enum

class WindPosition(Enum):
    EAST = 0
    SOUTH = 1
    WEST = 2
    NORTH = 3
    
    def __str__(self):
        return self.name
    
    def next(self):
        return WindPosition((self.value - 1) % 4)

class Player:
    def __init__(self, name, position):  # name: "玩家A"，position: 0~3 (东南西北)
        self.name = name
        self.position = position
        self.hand = []     # 当前手牌
        self.melds = []    # 副露区（碰/杠的牌）
    
    def can_pon(self, tile):
        return self.hand.count(tile) >= 2

    def can_kan(self, tile):
        return self.hand.count(tile) >= 3

    def discard_tile(self):
        # AI 选择打出一张牌，调试阶段可以简单选择手牌中第一张
        return self.hand[0]

"""动作的表示与编号。

每个动作既是 (type, tile) 二元组,也对应一个 0..114 的整数编号,
编号固定不变,供神经网络输出层和牌谱使用。

    编号        动作                tile 含义
    0  .. 26    DISCARD   出牌       打出的牌
    27 .. 53    AN_GANG   暗杠       杠的牌
    54 .. 80    JIA_GANG  加杠       杠的牌
    81          PONG      碰         -
    82          MING_GANG 直杠       -
    83          HU        胡         -
    84          PASS      过         -
    85 .. 87    CHOOSE_VOID 定缺     花色 0/1/2
    88 .. 114   EXCHANGE  换三张选牌  选出的牌(每次选一张,连选三次)
"""
from __future__ import annotations

from enum import IntEnum
from typing import NamedTuple

from .tiles import NUM_SUITS, NUM_TILE_TYPES, SUIT_NAMES, tile_name


class ActionType(IntEnum):
    DISCARD = 0
    AN_GANG = 1
    JIA_GANG = 2
    PONG = 3
    MING_GANG = 4
    HU = 5
    PASS = 6
    CHOOSE_VOID = 7
    EXCHANGE = 8


_DISCARD_BASE = 0
_AN_GANG_BASE = _DISCARD_BASE + NUM_TILE_TYPES  # 27
_JIA_GANG_BASE = _AN_GANG_BASE + NUM_TILE_TYPES  # 54
_PONG_ID = _JIA_GANG_BASE + NUM_TILE_TYPES  # 81
_MING_GANG_ID = _PONG_ID + 1  # 82
_HU_ID = _MING_GANG_ID + 1  # 83
_PASS_ID = _HU_ID + 1  # 84
_VOID_BASE = _PASS_ID + 1  # 85
_EXCHANGE_BASE = _VOID_BASE + NUM_SUITS  # 88
NUM_ACTIONS = _EXCHANGE_BASE + NUM_TILE_TYPES  # 115

_TILE_BASES = {
    ActionType.DISCARD: _DISCARD_BASE,
    ActionType.AN_GANG: _AN_GANG_BASE,
    ActionType.JIA_GANG: _JIA_GANG_BASE,
    ActionType.EXCHANGE: _EXCHANGE_BASE,
}
_FIXED_IDS = {
    ActionType.PONG: _PONG_ID,
    ActionType.MING_GANG: _MING_GANG_ID,
    ActionType.HU: _HU_ID,
    ActionType.PASS: _PASS_ID,
}
_LABELS = {
    ActionType.DISCARD: "打",
    ActionType.AN_GANG: "暗杠",
    ActionType.JIA_GANG: "加杠",
    ActionType.PONG: "碰",
    ActionType.MING_GANG: "杠",
    ActionType.HU: "胡",
    ActionType.PASS: "过",
    ActionType.CHOOSE_VOID: "定缺",
    ActionType.EXCHANGE: "换",
}


class Action(NamedTuple):
    type: ActionType
    tile: int = -1  # 牌编号;定缺时是花色;碰/直杠/胡/过 时为 -1

    @property
    def id(self) -> int:
        if self.type in _TILE_BASES:
            return _TILE_BASES[self.type] + self.tile
        if self.type == ActionType.CHOOSE_VOID:
            return _VOID_BASE + self.tile
        return _FIXED_IDS[self.type]

    @staticmethod
    def from_id(action_id: int) -> "Action":
        if not 0 <= action_id < NUM_ACTIONS:
            raise ValueError(f"动作编号越界: {action_id}")
        if action_id < _AN_GANG_BASE:
            return Action(ActionType.DISCARD, action_id - _DISCARD_BASE)
        if action_id < _JIA_GANG_BASE:
            return Action(ActionType.AN_GANG, action_id - _AN_GANG_BASE)
        if action_id < _PONG_ID:
            return Action(ActionType.JIA_GANG, action_id - _JIA_GANG_BASE)
        if action_id == _PONG_ID:
            return PONG
        if action_id == _MING_GANG_ID:
            return MING_GANG
        if action_id == _HU_ID:
            return HU
        if action_id == _PASS_ID:
            return PASS
        if action_id < _EXCHANGE_BASE:
            return Action(ActionType.CHOOSE_VOID, action_id - _VOID_BASE)
        return Action(ActionType.EXCHANGE, action_id - _EXCHANGE_BASE)

    def __str__(self) -> str:
        label = _LABELS[self.type]
        if self.type in _TILE_BASES:
            return f"{label}{tile_name(self.tile)}"
        if self.type == ActionType.CHOOSE_VOID:
            return f"{label}{SUIT_NAMES[self.tile]}"
        return label


PONG = Action(ActionType.PONG)
MING_GANG = Action(ActionType.MING_GANG)
HU = Action(ActionType.HU)
PASS = Action(ActionType.PASS)


def discard(tile: int) -> Action:
    return Action(ActionType.DISCARD, tile)


def an_gang(tile: int) -> Action:
    return Action(ActionType.AN_GANG, tile)


def jia_gang(tile: int) -> Action:
    return Action(ActionType.JIA_GANG, tile)


def choose_void(suit: int) -> Action:
    return Action(ActionType.CHOOSE_VOID, suit)


def exchange(tile: int) -> Action:
    return Action(ActionType.EXCHANGE, tile)

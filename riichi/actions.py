"""动作的表示与编号。

每个动作是 (type, arg) 二元组,也对应一个 0..118 的整数编号。
编号固定不变,供神经网络输出层和牌谱使用。

    编号          动作                    arg 含义
    0   .. 36    DISCARD   出牌           牌(0..33 普通,34..36 赤 5)
    37  .. 70    ANKAN     暗杠           牌的种类
    71  .. 104   KAKAN     加杠           牌的种类
    105          RIICHI    宣言立直        -(下一步再选打哪张)
    106 .. 111   CHI       吃             形状 * 2 + 是否用赤 5
                                         形状: 0 被吃的牌最小、1 在中间、2 最大
    112 .. 113   PON       碰             是否用赤 5
    114          DAIMINKAN 大明杠          -
    115          TSUMO     自摸           -
    116          RON       荣和(含抢杠)    -
    117          KYUUSHU   九种九牌        -
    118          PASS      过             -

"用赤 5"指从手里拿出去的那两张牌里有赤 5。
"""
from __future__ import annotations

from enum import IntEnum
from typing import NamedTuple

from .tiles import NUM_KINDS, NUM_TILE_CODES, tile_name


class ActionType(IntEnum):
    DISCARD = 0
    ANKAN = 1
    KAKAN = 2
    RIICHI = 3
    CHI = 4
    PON = 5
    DAIMINKAN = 6
    TSUMO = 7
    RON = 8
    KYUUSHU = 9
    PASS = 10


_DISCARD_BASE = 0
_ANKAN_BASE = _DISCARD_BASE + NUM_TILE_CODES  # 37
_KAKAN_BASE = _ANKAN_BASE + NUM_KINDS  # 71
_RIICHI_ID = _KAKAN_BASE + NUM_KINDS  # 105
_CHI_BASE = _RIICHI_ID + 1  # 106
_PON_BASE = _CHI_BASE + 6  # 112
_DAIMINKAN_ID = _PON_BASE + 2  # 114
_TSUMO_ID = _DAIMINKAN_ID + 1  # 115
_RON_ID = _TSUMO_ID + 1  # 116
_KYUUSHU_ID = _RON_ID + 1  # 117
_PASS_ID = _KYUUSHU_ID + 1  # 118
NUM_ACTIONS = _PASS_ID + 1  # 119

_ARG_BASES = {
    ActionType.DISCARD: _DISCARD_BASE,
    ActionType.ANKAN: _ANKAN_BASE,
    ActionType.KAKAN: _KAKAN_BASE,
    ActionType.CHI: _CHI_BASE,
    ActionType.PON: _PON_BASE,
}
_FIXED_IDS = {
    ActionType.RIICHI: _RIICHI_ID,
    ActionType.DAIMINKAN: _DAIMINKAN_ID,
    ActionType.TSUMO: _TSUMO_ID,
    ActionType.RON: _RON_ID,
    ActionType.KYUUSHU: _KYUUSHU_ID,
    ActionType.PASS: _PASS_ID,
}
_LABELS = {
    ActionType.DISCARD: "打",
    ActionType.ANKAN: "暗杠",
    ActionType.KAKAN: "加杠",
    ActionType.RIICHI: "立直",
    ActionType.CHI: "吃",
    ActionType.PON: "碰",
    ActionType.DAIMINKAN: "杠",
    ActionType.TSUMO: "自摸",
    ActionType.RON: "荣和",
    ActionType.KYUUSHU: "九种九牌",
    ActionType.PASS: "过",
}
CHI_SHAPE_NAMES = ("被吃的牌最小", "被吃的牌在中间", "被吃的牌最大")


class Action(NamedTuple):
    type: ActionType
    arg: int = -1  # 出牌: 牌;暗杠/加杠: 种类;吃: 形状*2+赤;碰: 赤;其余 -1

    @property
    def id(self) -> int:
        base = _ARG_BASES.get(self.type)
        if base is not None:
            return base + self.arg
        return _FIXED_IDS[self.type]

    @staticmethod
    def from_id(action_id: int) -> "Action":
        return _ALL[action_id]

    @property
    def tile(self) -> int:
        """出牌、暗杠、加杠涉及的牌;其余为 -1。"""
        if self.type in (ActionType.DISCARD, ActionType.ANKAN, ActionType.KAKAN):
            return self.arg
        return -1

    def __str__(self) -> str:
        label = _LABELS[self.type]
        if self.type in (ActionType.DISCARD, ActionType.ANKAN, ActionType.KAKAN):
            return f"{label}{tile_name(self.arg)}"
        if self.type == ActionType.CHI:
            return f"{label}({CHI_SHAPE_NAMES[self.arg // 2]}{',用赤5' if self.arg % 2 else ''})"
        if self.type == ActionType.PON:
            return label + ("(用赤5)" if self.arg else "")
        return label


def _build() -> list:
    out = [Action(ActionType.DISCARD, t) for t in range(NUM_TILE_CODES)]
    out += [Action(ActionType.ANKAN, k) for k in range(NUM_KINDS)]
    out += [Action(ActionType.KAKAN, k) for k in range(NUM_KINDS)]
    out.append(Action(ActionType.RIICHI))
    out += [Action(ActionType.CHI, i) for i in range(6)]
    out += [Action(ActionType.PON, i) for i in range(2)]
    out += [
        Action(ActionType.DAIMINKAN),
        Action(ActionType.TSUMO),
        Action(ActionType.RON),
        Action(ActionType.KYUUSHU),
        Action(ActionType.PASS),
    ]
    return out


_ALL = _build()
assert len(_ALL) == NUM_ACTIONS and all(a.id == i for i, a in enumerate(_ALL))

RIICHI = _ALL[_RIICHI_ID]
DAIMINKAN = _ALL[_DAIMINKAN_ID]
TSUMO = _ALL[_TSUMO_ID]
RON = _ALL[_RON_ID]
KYUUSHU = _ALL[_KYUUSHU_ID]
PASS = _ALL[_PASS_ID]


def discard(tile: int) -> Action:
    return _ALL[_DISCARD_BASE + tile]


def ankan(kind: int) -> Action:
    return _ALL[_ANKAN_BASE + kind]


def kakan(kind: int) -> Action:
    return _ALL[_KAKAN_BASE + kind]


def chi(shape: int, red: bool = False) -> Action:
    return _ALL[_CHI_BASE + shape * 2 + int(red)]


def pon(red: bool = False) -> Action:
    return _ALL[_PON_BASE + int(red)]

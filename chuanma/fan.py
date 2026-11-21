"""番型判断与番数计算。

采用"加番"体系: 胡牌得分 = 底分 * 2^min(总番数, 封顶)。
总番数 = 牌型番 + 附加番,同一手牌有多种拆法时取番数最高的一种。
完整番表见 docs/rules.md。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional, Sequence, Tuple

from .config import RuleConfig
from .hand import is_seven_pairs, standard_decompositions, winning_tiles
from .tiles import NUM_RANKS


class MeldType(IntEnum):
    PONG = 0  # 碰
    MING_GANG = 1  # 直杠(别人打出,自己手里有三张)
    AN_GANG = 2  # 暗杠
    JIA_GANG = 3  # 加杠(碰过之后摸到第四张)


@dataclass
class Meld:
    type: MeldType
    tile: int
    from_seat: int  # 牌来自哪个座位;暗杠是自己

    @property
    def is_gang(self) -> bool:
        return self.type != MeldType.PONG

    @property
    def size(self) -> int:
        return 4 if self.is_gang else 3


@dataclass(frozen=True)
class WinContext:
    """胡牌时的场况,决定附加番。"""

    zimo: bool = False
    tianhu: bool = False
    dihu: bool = False
    gang_shang_hua: bool = False  # 杠后补牌自摸
    gang_shang_pao: bool = False  # 别人杠后打出的牌点炮
    qiang_gang: bool = False  # 抢杠胡
    haidi: bool = False  # 最后一张牌(自摸=海底捞月,点炮=海底炮)


@dataclass(frozen=True)
class FanResult:
    fan: int  # 未封顶的总番数
    capped_fan: int  # 封顶后的番数
    points: int  # 底分 * 2^capped_fan(不含自摸加底)
    names: Tuple[str, ...]  # 番型明细


# 牌型番
FAN_PING_HU = 0
FAN_DUI_DUI_HU = 1
FAN_JIANG_DUI = 3  # 已含对对胡
FAN_JIN_GOU_DIAO = 1  # 叠加在对对胡/将对上
FAN_DAI_YAO_JIU = 2
FAN_QI_DUI = 2
# 附加番
FAN_QING_YI_SE = 2
FAN_GEN = 1  # 每一根
FAN_MEN_QING = 1
FAN_ZHONG_ZHANG = 1
FAN_TIAN_HU = 5
FAN_DI_HU = 5
FAN_GANG_SHANG_HUA = 1
FAN_GANG_SHANG_PAO = 1
FAN_QIANG_GANG = 1
FAN_HAIDI = 1
FAN_ZIMO = 1  # 仅 zimo_mode == "jia_fan"


def evaluate_fan(
    counts: Sequence[int],
    melds: Sequence[Meld],
    ctx: WinContext,
    config: RuleConfig,
) -> FanResult:
    """计算一手胡牌的番数。counts 是含胡牌张的手牌计数,不含副露。

    不是胡型时抛出 ValueError。
    """
    total = list(counts)
    for m in melds:
        total[m.tile] += m.size

    suits = set()
    has_terminal = False
    all_258 = True
    for t, n in enumerate(total):
        if n:
            suits.add(t // NUM_RANKS)
            rank = t % NUM_RANKS + 1
            if rank in (1, 9):
                has_terminal = True
            if rank not in (2, 5, 8):
                all_258 = False
    gen = sum(1 for n in total if n == 4)
    concealed = all(m.type == MeldType.AN_GANG for m in melds)

    # --- 牌型番: 列出所有候选,取总番最高者 ---
    candidates: List[Tuple[int, List[str], bool]] = []  # (番, 名称, 是否七对)

    if not melds and is_seven_pairs(counts):
        candidates.append((FAN_QI_DUI, ["七对"], True))

    meld_ranks_terminal = all((m.tile % NUM_RANKS + 1) in (1, 9) for m in melds)
    for pair, hand_melds in standard_decompositions(counts):
        fan = 0
        names: List[str] = []
        if all(is_triplet for is_triplet, _ in hand_melds):
            if all_258:
                fan += FAN_JIANG_DUI
                names.append("将对")
            else:
                fan += FAN_DUI_DUI_HU
                names.append("对对胡")
            if len(melds) == 4:
                fan += FAN_JIN_GOU_DIAO
                names.append("金钩钓")
        if has_terminal and meld_ranks_terminal and _all_groups_have_terminal(pair, hand_melds):
            fan += FAN_DAI_YAO_JIU
            names.append("带幺九")
        if not names:
            names.append("平胡")
        candidates.append((fan, names, False))

    if not candidates:
        raise ValueError("不是胡型,无法计番")

    best_fan = -1
    best_names: List[str] = []
    for fan, names, is_seven in candidates:
        names = list(names)
        extra_gen = gen
        if is_seven and gen >= 1:
            # 七对里有四张相同的牌叫龙七对,这一根的 1 番并入牌型名
            names = ["龙七对"]
            fan += FAN_GEN
            extra_gen = gen - 1
        if len(suits) == 1:
            fan += FAN_QING_YI_SE
            names.append("清一色")
        if extra_gen:
            fan += FAN_GEN * extra_gen
            names.append(f"根×{extra_gen}")
        if config.men_qing_zhong_zhang:
            if concealed and not is_seven:
                fan += FAN_MEN_QING
                names.append("门清")
            if not has_terminal:
                fan += FAN_ZHONG_ZHANG
                names.append("中张")
        if fan > best_fan:
            best_fan, best_names = fan, names

    fan, names = best_fan, best_names

    # --- 场况附加番 ---
    if config.tian_di_hu:
        if ctx.tianhu:
            fan += FAN_TIAN_HU
            names.append("天胡")
        elif ctx.dihu:
            fan += FAN_DI_HU
            names.append("地胡")
    if ctx.gang_shang_hua:
        fan += FAN_GANG_SHANG_HUA
        names.append("杠上花")
    if ctx.gang_shang_pao:
        fan += FAN_GANG_SHANG_PAO
        names.append("杠上炮")
    if ctx.qiang_gang:
        fan += FAN_QIANG_GANG
        names.append("抢杠胡")
    if ctx.haidi and config.haidi:
        fan += FAN_HAIDI
        names.append("海底捞月" if ctx.zimo else "海底炮")
    if ctx.zimo and config.zimo_mode == "jia_fan":
        fan += FAN_ZIMO
        names.append("自摸")

    capped = min(fan, config.max_fan)
    return FanResult(fan, capped, config.base_score * (1 << capped), tuple(names))


def _all_groups_have_terminal(pair: int, hand_melds) -> bool:
    """将牌和手里每组面子是否都带 1 或 9。"""
    if (pair % NUM_RANKS + 1) not in (1, 9):
        return False
    for is_triplet, tile in hand_melds:
        rank = tile % NUM_RANKS + 1
        if is_triplet:
            if rank not in (1, 9):
                return False
        elif rank not in (1, 7):  # 顺子只能是 123 或 789
            return False
    return True


def best_ting(
    counts: Sequence[int],
    melds: Sequence[Meld],
    void_suit: int,
    config: RuleConfig,
) -> Optional[Tuple[int, FanResult]]:
    """查大叫用: 听牌时返回 (听的牌, 番数结果) 中得分最高的一个,没听牌返回 None。

    按点炮胡计算,不含任何场况附加番。
    """
    meld_tiles = [m.tile for m in melds for _ in range(m.size)]
    waits = winning_tiles(counts, len(melds), void_suit, meld_tiles)
    if not waits:
        return None
    c = list(counts)
    ctx = WinContext(zimo=False)
    best: Optional[Tuple[int, FanResult]] = None
    for t in waits:
        c[t] += 1
        result = evaluate_fan(c, melds, ctx, config)
        c[t] -= 1
        if best is None or result.fan > best[1].fan:
            best = (t, result)
    return best


__all__ = [
    "Meld",
    "MeldType",
    "WinContext",
    "FanResult",
    "evaluate_fan",
    "best_ting",
]

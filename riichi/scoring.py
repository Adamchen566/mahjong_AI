"""役、符、番、点数。

evaluate() 给一手和了的牌算出最高的那种算法;不成和牌型或者没有役时返回 None。
规则见 docs/riichi-rules.md 第 4、5 节。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Sequence, Tuple

from .config import RuleConfig
from .hand import CHI, PON, decompose, is_chiitoi, is_kokushi
from .tiles import GREENS, HONORS, TERMINALS, WIND_NAMES, YAOCHU_SET, kind_of

KAN = 2  # 面子种类: 在 hand.CHI / hand.PON 之外再加一个杠

_DEFAULT_CONFIG = RuleConfig()
_DRAGON_NAMES = {31: "役牌 白", 32: "役牌 发", 33: "役牌 中"}


class MeldType(IntEnum):
    CHI = 0
    PON = 1
    DAIMINKAN = 2
    ANKAN = 3
    KAKAN = 4


@dataclass(frozen=True)
class Meld:
    """一组副露。tiles 是具体的牌(含赤牌编号),包括被吃碰杠来的那张。"""

    type: MeldType
    tiles: Tuple[int, ...]
    called: int = -1  # 从别人那里拿来的那张;暗杠为 -1
    from_seat: int = -1  # 那张牌是谁打的;暗杠为 -1

    @property
    def kind(self) -> int:
        """刻子、杠: 牌的种类;顺子: 最小的那张的种类。"""
        return min(kind_of(t) for t in self.tiles)

    @property
    def is_kan(self) -> bool:
        return self.type in (MeldType.DAIMINKAN, MeldType.ANKAN, MeldType.KAKAN)

    @property
    def is_open(self) -> bool:
        return self.type != MeldType.ANKAN


@dataclass
class WinContext:
    """和牌时的场况。"""

    tsumo: bool = False
    riichi: int = 0  # 0 没立直,1 立直,2 双立直
    ippatsu: bool = False
    rinshan: bool = False
    chankan: bool = False
    haitei: bool = False  # 海底摸月
    houtei: bool = False  # 河底捞鱼
    tenhou: bool = False
    chiihou: bool = False
    seat_wind: int = 0  # 0 东 1 南 2 西 3 北
    round_wind: int = 0
    dora: int = 0  # 宝牌张数(含杠宝)
    ura: int = 0  # 里宝牌张数
    aka: int = 0  # 赤宝牌张数


@dataclass
class HandValue:
    han: int  # 总番数(含宝牌);役满时为 0
    fu: int  # 役满时为 0
    yaku: List[Tuple[str, int]]  # (名称, 番数);役满的番数记成 13
    yakuman: int  # 役满倍数;数役满也是 0
    base: int  # 基本点
    limit: str  # "" / 满贯 / 跳满 / 倍满 / 三倍满 / 数役满 / 役满 / N倍役满
    yaku_han: int = 0  # 不含宝牌的番数
    yakuman_names: List[str] = field(default_factory=list)

    @property
    def names(self) -> List[str]:
        return [n for n, _ in self.yaku]


def ceil100(x: int) -> int:
    return -(-x // 100) * 100


def base_points(han: int, fu: int, kazoe: bool = True) -> int:
    """基本点。闲家荣和 ×4、庄家荣和 ×6;自摸时闲家付 ×1、庄家付 ×2。"""
    if han >= 13:
        return 8000 if kazoe else 6000
    if han >= 11:
        return 6000
    if han >= 8:
        return 4000
    if han >= 6:
        return 3000
    if han >= 5:
        return 2000
    return min(2000, fu * 2 ** (han + 2))


def limit_name(han: int, fu: int, kazoe: bool = True) -> str:
    if han >= 13:
        return "数役满" if kazoe else "三倍满"
    if han >= 11:
        return "三倍满"
    if han >= 8:
        return "倍满"
    if han >= 6:
        return "跳满"
    if han >= 5 or fu * 2 ** (han + 2) >= 2000:
        return "满贯"
    return ""


def ron_points(base: int, dealer: bool) -> int:
    """荣和时放铳者付的点数(不含本场)。"""
    return ceil100(base * (6 if dealer else 4))


def tsumo_points(base: int, winner_is_dealer: bool, payer_is_dealer: bool) -> int:
    """自摸时某一家付的点数(不含本场)。"""
    return ceil100(base * (2 if winner_is_dealer or payer_is_dealer else 1))


def _situational(ctx: WinContext, menzen: bool) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    if ctx.riichi == 2:
        out.append(("双立直", 2))
    elif ctx.riichi == 1:
        out.append(("立直", 1))
    if ctx.ippatsu and ctx.riichi:
        out.append(("一发", 1))
    if ctx.tsumo and menzen:
        out.append(("门前清自摸和", 1))
    if ctx.rinshan:
        out.append(("岭上开花", 1))
    if ctx.chankan:
        out.append(("抢杠", 1))
    if ctx.haitei:
        out.append(("海底摸月", 1))
    if ctx.houtei:
        out.append(("河底捞鱼", 1))
    return out


def _flush(total: Sequence[int]) -> Tuple[int, bool]:
    """(用到了几门数牌, 有没有字牌)。"""
    suits = 0
    for g in range(3):
        if any(total[g * 9 : g * 9 + 9]):
            suits += 1
    return suits, any(total[27:34])


def _yakuman_value(names: List[str]) -> HandValue:
    n = len(names)
    return HandValue(
        han=0,
        fu=0,
        yaku=[(name, 13) for name in names],
        yakuman=n,
        base=8000 * n,
        limit="役满" if n == 1 else f"{n}倍役满",
        yakuman_names=list(names),
    )


def _finish(yaku: List[Tuple[str, int]], fu: int, ctx: WinContext, config: RuleConfig) -> Optional[HandValue]:
    yaku_han = sum(h for _, h in yaku)
    if yaku_han == 0:
        return None
    yaku = list(yaku)
    if ctx.dora:
        yaku.append(("宝牌", ctx.dora))
    if ctx.aka:
        yaku.append(("赤宝牌", ctx.aka))
    if ctx.ura:
        yaku.append(("里宝牌", ctx.ura))
    han = yaku_han + ctx.dora + ctx.aka + ctx.ura
    return HandValue(
        han=han,
        fu=fu,
        yaku=yaku,
        yakuman=0,
        base=base_points(han, fu, config.kazoe),
        limit=limit_name(han, fu, config.kazoe),
        yaku_han=yaku_han,
    )


def _eval_chiitoi(counts: Sequence[int], ctx: WinContext, config: RuleConfig) -> Optional[HandValue]:
    yakuman: List[str] = []
    if ctx.tenhou:
        yakuman.append("天和")
    if ctx.chiihou:
        yakuman.append("地和")
    suits, honors = _flush(counts)
    if suits == 0:
        yakuman.append("字一色")
    if yakuman:
        return _yakuman_value(yakuman)
    yaku = _situational(ctx, True)
    yaku.append(("七对子", 2))
    held = [k for k in range(34) if counts[k]]
    if all(k not in YAOCHU_SET for k in held):
        yaku.append(("断幺九", 1))
    if all(k in YAOCHU_SET for k in held):
        yaku.append(("混老头", 2))
    if suits == 1:
        yaku.append(("混一色", 3) if honors else ("清一色", 6))
    return _finish(yaku, 25, ctx, config)


def _eval_standard(
    pair: int,
    sets: Sequence[Tuple[int, int]],
    wait_set: Optional[Tuple[int, int]],
    counts: Sequence[int],
    melds: Sequence[Meld],
    total: Sequence[int],
    win_kind: int,
    ctx: WinContext,
    config: RuleConfig,
    menzen: bool,
) -> Optional[HandValue]:
    # 全部面子: (种类, 牌, 是否暗)
    groups: List[Tuple[int, int, bool]] = []
    ron_opened = False
    for typ, k in sets:
        concealed = True
        if not ctx.tsumo and typ == PON and wait_set == (PON, k) and not ron_opened:
            concealed = False  # 荣和凑成的刻子算明刻
            ron_opened = True
        groups.append((typ, k, concealed))
    for m in melds:
        if m.type == MeldType.CHI:
            groups.append((CHI, m.kind, False))
        elif m.type == MeldType.PON:
            groups.append((PON, m.kind, False))
        else:
            groups.append((KAN, m.kind, m.type == MeldType.ANKAN))

    chis = [k for typ, k, _ in groups if typ == CHI]
    triplets = [k for typ, k, _ in groups if typ != CHI]  # 刻子和杠
    concealed_triplets = sum(1 for typ, _, c in groups if typ != CHI and c)
    kans = sum(1 for typ, _, _ in groups if typ == KAN)
    suits, honors = _flush(total)
    seat_kind = 27 + ctx.seat_wind
    round_kind = 27 + ctx.round_wind

    # ---- 役满 ----
    yakuman: List[str] = []
    if ctx.tenhou:
        yakuman.append("天和")
    if ctx.chiihou:
        yakuman.append("地和")
    if concealed_triplets == 4:
        yakuman.append("四暗刻")
    if all(d in triplets for d in (31, 32, 33)):
        yakuman.append("大三元")
    wind_triplets = sum(1 for k in triplets if 27 <= k <= 30)
    if wind_triplets == 4:
        yakuman.append("大四喜")
    elif wind_triplets == 3 and 27 <= pair <= 30:
        yakuman.append("小四喜")
    if suits == 0:
        yakuman.append("字一色")
    if all(total[k] == 0 for k in range(34) if k not in GREENS):
        yakuman.append("绿一色")
    if all(total[k] == 0 for k in range(34) if k not in TERMINALS):
        yakuman.append("清老头")
    if not melds and suits == 1 and not honors:
        g = next(g for g in range(3) if any(counts[g * 9 : g * 9 + 9]))
        seg = counts[g * 9 : g * 9 + 9]
        if seg[0] >= 3 and seg[8] >= 3 and all(seg[1:8]):
            yakuman.append("九莲宝灯")
    if kans == 4:
        yakuman.append("四杠子")
    if yakuman:
        return _yakuman_value(yakuman)

    # ---- 符 ----
    pair_fu = 0
    if pair >= 31:
        pair_fu += 2
    if pair == seat_kind:
        pair_fu += 2
    if pair == round_kind:
        pair_fu += 2
    wait_fu = 0
    if wait_set is None:
        wait_fu = 2  # 单骑
    elif wait_set[0] == CHI:
        k = wait_set[1]
        if win_kind == k + 1:
            wait_fu = 2  # 嵌张
        elif (win_kind == k + 2 and k % 9 == 0) or (win_kind == k and k % 9 == 6):
            wait_fu = 2  # 边张
    set_fu = 0
    for typ, k, concealed in groups:
        if typ == CHI:
            continue
        f = 4 if concealed else 2
        if k in YAOCHU_SET:
            f *= 2
        if typ == KAN:
            f *= 4
        set_fu += f

    pinfu = menzen and len(chis) == 4 and pair_fu == 0 and wait_fu == 0

    if pinfu:
        fu = 20 if ctx.tsumo else 30
    else:
        fu = 20 + set_fu + pair_fu + wait_fu
        if ctx.tsumo:
            fu += 2
        elif menzen:
            fu += 10
        if not menzen and fu == 20:
            fu = 30  # 副露的平和形
        fu = -(-fu // 10) * 10

    # ---- 役 ----
    yaku = _situational(ctx, menzen)
    if pinfu:
        yaku.append(("平和", 1))
    if (menzen or config.kuitan) and all(total[k] == 0 for k in YAOCHU_SET):
        yaku.append(("断幺九", 1))
    if menzen:
        same = sum(chis.count(k) // 2 for k in set(chis))
        if same >= 2:
            yaku.append(("二杯口", 3))
        elif same == 1:
            yaku.append(("一杯口", 1))
    for k in triplets:
        if k in _DRAGON_NAMES:
            yaku.append((_DRAGON_NAMES[k], 1))
        if k == seat_kind:
            yaku.append((f"自风 {WIND_NAMES[ctx.seat_wind]}", 1))
        if k == round_kind:
            yaku.append((f"场风 {WIND_NAMES[ctx.round_wind]}", 1))
    down = 0 if menzen else 1  # 食下
    if any(r in chis and 9 + r in chis and 18 + r in chis for r in range(7)):
        yaku.append(("三色同顺", 2 - down))
    if any(g * 9 in chis and g * 9 + 3 in chis and g * 9 + 6 in chis for g in range(3)):
        yaku.append(("一气通贯", 2 - down))
    all_yaochu_groups = pair in YAOCHU_SET and all(
        (k % 9 in (0, 6)) if typ == CHI else (k in YAOCHU_SET) for typ, k, _ in groups
    )
    if all_yaochu_groups and chis:
        yaku.append(("混全带幺九", 2 - down) if honors else ("纯全带幺九", 3 - down))
    if not chis:
        yaku.append(("对对和", 2))
    if concealed_triplets == 3:
        yaku.append(("三暗刻", 2))
    if any(r in triplets and 9 + r in triplets and 18 + r in triplets for r in range(9)):
        yaku.append(("三色同刻", 2))
    if kans == 3:
        yaku.append(("三杠子", 2))
    if sum(1 for k in triplets if k >= 31) == 2 and pair >= 31:
        yaku.append(("小三元", 2))
    if all_yaochu_groups and not chis:
        yaku.append(("混老头", 2))
    if suits == 1:
        yaku.append(("混一色", 3 - down) if honors else ("清一色", 6 - down))
    return _finish(yaku, fu, ctx, config)


def evaluate(
    counts: Sequence[int],
    melds: Sequence[Meld],
    win_kind: int,
    ctx: WinContext,
    config: Optional[RuleConfig] = None,
) -> Optional[HandValue]:
    """算一手和牌的价值,取点数最高的拆法。

    counts: 手里的牌按种类计数,**已经包含和的那张**(14 - 3*副露数 张)。
    win_kind: 和的那张牌的种类。
    返回 None 表示不是和牌型,或者没有役。
    """
    config = config or _DEFAULT_CONFIG
    menzen = all(m.type == MeldType.ANKAN for m in melds)
    best: Optional[HandValue] = None

    def consider(v: Optional[HandValue]) -> None:
        nonlocal best
        if v is None:
            return
        # 点数相同时优先役满(例如四暗刻和数役满都是 8000 基本点,记作四暗刻)
        if best is None or (v.base, v.yakuman, v.han, v.fu) > (best.base, best.yakuman, best.han, best.fu):
            best = v

    if not melds:
        if is_kokushi(counts):
            names = ["国士无双"]
            if ctx.tenhou:
                names.insert(0, "天和")
            if ctx.chiihou:
                names.insert(0, "地和")
            return _yakuman_value(names)
        if is_chiitoi(counts):
            consider(_eval_chiitoi(counts, ctx, config))

    decs = decompose(counts)
    if decs:
        total = list(counts)
        for m in melds:
            for t in m.tiles:
                total[kind_of(t)] += 1
        for pair, sets in decs:
            options = set()
            if pair == win_kind:
                options.add(None)
            for typ, k in sets:
                if (typ == PON and k == win_kind) or (typ == CHI and k <= win_kind <= k + 2):
                    options.add((typ, k))
            for opt in options:
                consider(_eval_standard(pair, sets, opt, counts, melds, total, win_kind, ctx, config, menzen))
    return best

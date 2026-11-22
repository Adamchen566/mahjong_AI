"""日麻: 每一个役、符的每一项、点数表。规则见 docs/riichi-rules.md 第 4、5 节。

value(手牌含和的那张, 和的那张, 副露, **场况)。默认是闲家(南家)、东场、荣和。
"""
import pytest

from riichi import RuleConfig
from riichi.scoring import MeldType, base_points, ron_points, tsumo_points

from riichi_helpers import chi, kan, names, pon, value

S = 1  # 默认南家


# ---------------------------------------------------------------- 一番役


def test_riichi_and_pinfu():
    v = value("123m456p789s345s22p", "3s", riichi=1, seat_wind=S)
    assert names(v) == {"立直", "平和"} and (v.han, v.fu) == (2, 30)


def test_ippatsu_needs_riichi():
    assert "一发" in names(value("123m456p789s345s22p", "3s", riichi=1, ippatsu=True, seat_wind=S))
    assert "一发" not in names(value("123m456p789s345s22p", "3s", riichi=0, ippatsu=True, tsumo=True, seat_wind=S))


def test_menzen_tsumo_and_pinfu_tsumo_is_20_fu():
    v = value("123m456p789s345s22p", "3s", tsumo=True, seat_wind=S)
    assert names(v) == {"门前清自摸和", "平和"} and (v.han, v.fu) == (2, 20)


def test_pinfu_ron_30_fu():
    v = value("123m456p789s345s22p", "3s", seat_wind=S)
    assert names(v) == {"平和"} and (v.han, v.fu) == (1, 30)


@pytest.mark.parametrize(
    "hand,win,why",
    [
        ("123m456p789s345s22p", "4s", "嵌张"),
        ("123m456p789s123s22p", "3s", "边张"),
        ("123m456p789s345s22p", "2p", "单骑"),
        ("123m456p789s345s55z", "3s", "役牌雀头"),
        ("123m456p789s345s22z", "3s", "自风雀头"),
        ("123m456p789s345s11z", "3s", "场风雀头"),
    ],
)
def test_not_pinfu(hand, win, why):
    v = value(hand, win, riichi=1, seat_wind=S)
    assert "平和" not in names(v), why


def test_pinfu_ambiguous_wait_takes_ryanmen():
    """23456 和 4: 可以看成嵌张也可以看成两面,取有平和的那种。"""
    v = value("234m456m789s345s22p", "4m", seat_wind=S)
    assert "平和" in names(v)


def test_tanyao_open_and_closed():
    assert names(value("234m456p678s345s22p", "3s", seat_wind=S)) == {"平和", "断幺九"}
    v = value("456p678s345s22p", "3s", melds=[chi("234m")], seat_wind=S)
    assert names(v) == {"断幺九"} and (v.han, v.fu) == (1, 30)
    assert value("456p678s345s22p", "3s", melds=[chi("234m")], seat_wind=S, config=RuleConfig(kuitan=False)) is None


def test_iipeikou_only_closed():
    v = value("112233m456p789s55p", "3m", seat_wind=S)
    assert names(v) == {"一杯口"} and (v.han, v.fu) == (1, 40)  # 边张 3m
    assert value("112233m456p55p", "3m", melds=[chi("789s")], seat_wind=S) is None


@pytest.mark.parametrize("tile,name", [("5z", "役牌 白"), ("6z", "役牌 发"), ("7z", "役牌 中")])
def test_dragon_triplets(tile, name):
    v = value(f"123m456p789s55p{tile * 3}", tile, seat_wind=S)
    assert names(v) == {name}


def test_wind_triplets():
    assert names(value("123m456p789s55p222z", "2z", seat_wind=1, round_wind=0)) == {"自风 南"}
    assert names(value("123m456p789s55p111z", "1z", seat_wind=1, round_wind=0)) == {"场风 东"}
    v = value("123m456p789s55p111z", "1z", seat_wind=0, round_wind=0)
    assert names(v) == {"自风 东", "场风 东"} and v.han == 2  # 连风牌
    assert value("123m456p789s55p333z", "3z", seat_wind=1, round_wind=0) is None  # 客风没役


def test_rinshan_chankan_haitei_houtei():
    base = dict(seat_wind=S, melds=[kan("9999s", MeldType.ANKAN)])
    assert "岭上开花" in names(value("123m456p789m55p", "5p", tsumo=True, rinshan=True, **base))
    assert names(value("123m456p678s345s22p", "3s", chankan=True, seat_wind=S)) >= {"抢杠"}
    assert "海底摸月" in names(value("123m456p789s234s55p", "5p", tsumo=True, haitei=True, seat_wind=S))
    assert names(value("123m456p789s234s55p", "5p", houtei=True, seat_wind=S)) == {"河底捞鱼"}


# ---------------------------------------------------------------- 二番以上


def test_double_riichi_replaces_riichi():
    v = value("123m456p789s345s22p", "3s", riichi=2, seat_wind=S)
    assert names(v) == {"双立直", "平和"} and v.han == 3


def test_chiitoitsu_25_fu():
    v = value("1122m3344p5566s77z", "7z", seat_wind=S)
    assert names(v) == {"七对子"} and (v.han, v.fu) == (2, 25)
    assert ron_points(v.base, False) == 1600


def test_sanshoku_kuisagari():
    assert ("三色同顺", 2) in value("123m123p123s789m55p", "5p", seat_wind=S).yaku
    assert ("三色同顺", 1) in value("123p123s789m55p", "5p", melds=[chi("123m")], seat_wind=S).yaku


def test_ittsu():
    assert ("一气通贯", 2) in value("123456789m234p55s", "9m", seat_wind=S).yaku
    assert ("一气通贯", 1) in value("456789m234p55s", "9m", melds=[chi("123m")], seat_wind=S).yaku


def test_chanta_and_junchan():
    assert ("混全带幺九", 2) in value("123m789p999s11p111z", "1z", seat_wind=S).yaku
    assert ("混全带幺九", 1) in value("789p999s11p111z", "1z", melds=[chi("123m")], seat_wind=S).yaku
    assert ("纯全带幺九", 3) in value("123m789m123p999s11s", "1s", seat_wind=S).yaku
    assert ("纯全带幺九", 2) in value("789m123p999s11s", "1s", melds=[chi("123m")], seat_wind=S).yaku


def test_toitoi():
    v = value("444m55z", "5z", melds=[pon("111m"), pon("222p"), pon("333s")], seat_wind=S)
    assert names(v) == {"对对和"}


def test_sanankou_ron_triplet_is_open():
    """荣和凑成的刻子算明刻;自摸就是暗刻。"""
    hand = "111m222p333s456m77z"
    assert "三暗刻" in names(value(hand, "3s", tsumo=True, seat_wind=S))
    assert "三暗刻" not in names(value(hand, "3s", seat_wind=S, riichi=1))
    assert "三暗刻" in names(value(hand, "4m", seat_wind=S, riichi=1))  # 和在顺子上


def test_sanshoku_doukou():
    v = value("222p222s123m55z", "5z", melds=[pon("222m")], seat_wind=S)
    assert "三色同刻" in names(v)


def test_sankantsu():
    melds = [kan("1111m"), kan("2222p"), kan("3333s", MeldType.ANKAN)]
    assert "三杠子" in names(value("456m77z", "7z", melds=melds, seat_wind=S))


def test_shousangen():
    v = value("55z666z777z123m456p", "4p", seat_wind=S)
    assert names(v) >= {"小三元", "役牌 发", "役牌 中"}


def test_honroutou():
    v = value("111m999p11z", "1z", melds=[pon("999s"), pon("777z")], seat_wind=S)
    assert names(v) >= {"混老头", "对对和"}
    assert "混老头" in names(value("1199m1199p11s1122z", "2z", seat_wind=S))  # 七对子形


def test_honitsu_and_chinitsu():
    assert ("混一色", 3) in value("123456m789m11z222z", "2z", seat_wind=S).yaku
    assert ("混一色", 2) in value("456m789m11z222z", "2z", melds=[chi("123m")], seat_wind=S).yaku
    assert ("清一色", 6) in value("223344m567m88m999m", "8m", seat_wind=S).yaku
    assert ("清一色", 5) in value("222m456m789m11m", "1m", melds=[chi("123m")], seat_wind=S).yaku


def test_ryanpeikou_replaces_iipeikou_and_chiitoi():
    v = value("112233m556677p44s", "4s", seat_wind=S)
    assert "二杯口" in names(v) and "一杯口" not in names(v) and "七对子" not in names(v)


# ---------------------------------------------------------------- 役满


@pytest.mark.parametrize(
    "hand,win,melds,ctx,name",
    [
        ("123m456p789s11222z", "2z", [], dict(tsumo=True, tenhou=True, seat_wind=0), "天和"),
        ("123m456p789s11222z", "2z", [], dict(tsumo=True, chiihou=True, seat_wind=1), "地和"),
        ("19m19p19s12345677z", "7z", [], {}, "国士无双"),
        ("19m19p19s1234567z1m", "1m", [], {}, "国士无双"),
        ("111m222p333s444m55z", "5z", [], {}, "四暗刻"),
        ("123m44p555z666z777z", "4p", [], {}, "大三元"),
        ("111z222z333z44z123m", "3m", [], {}, "小四喜"),
        ("111z222z333z444z55m", "5m", [], {}, "大四喜"),
        ("111z222z555z77z", "7z", [pon("666z")], {}, "字一色"),
        ("11223344556677z", "7z", [], {}, "字一色"),
        ("234s234s666s88s666z", "8s", [], {}, "绿一色"),
        ("111m999m111p999p11s", "1s", [], dict(tsumo=True), "四暗刻"),
        ("111m999m11s", "1s", [pon("111p"), pon("999p")], {}, "清老头"),
        ("11123455678999m", "5m", [], {}, "九莲宝灯"),
        ("55z", "5z", [kan("1111m"), kan("2222p"), kan("3333s", MeldType.ANKAN), kan("4444m")], {}, "四杠子"),
    ],
)
def test_yakuman(hand, win, melds, ctx, name):
    ctx = dict(ctx)
    ctx.setdefault("seat_wind", S)
    v = value(hand, win, melds=melds, **ctx)
    assert v is not None and name in v.yakuman_names
    assert v.han == 0 and v.base == 8000 * v.yakuman


def test_double_yakuman_counted_once_each():
    """十三面、四暗刻单骑、纯正九莲、大四喜都只算一倍。"""
    assert value("19m19p19s1234567z1m", "1m").yakuman == 1
    assert value("111m222p333s444m55z", "5z").yakuman == 1
    assert value("11123456789999m", "9m").yakuman == 1
    # 大四喜和四暗刻单骑各算一倍,两个不同的役满叠加成两倍
    v = value("111z222z333z444z55m", "5m")
    assert set(v.yakuman_names) == {"四暗刻", "大四喜"} and v.yakuman == 2


def test_yakuman_combination():
    v = value("555z666z777z11z", "1z", melds=[pon("222z")])
    assert set(v.yakuman_names) == {"大三元", "字一色"} and v.base == 16000


def test_yakuman_ignores_normal_yaku_and_dora():
    v = value("111m222p333s444m55z", "5z", riichi=1, dora=4)
    assert v.yaku == [("四暗刻", 13)]


def test_green_without_hatsu():
    assert "绿一色" in value("234s234s666s88s444s", "8s").yakuman_names


def test_chuuren_needs_closed():
    assert value("11123455678999m", "5m").yakuman_names == ["九莲宝灯"]
    v = value("11155678999m", "5m", melds=[chi("234m")])
    assert v is not None and not v.yakuman


def test_kazoe_yakuman_and_switch():
    v = value("11122233345699m", "9m", riichi=1, dora=6)  # 清一色 6 + 立直 1 + 宝牌 6 = 13
    assert v.han >= 13 and v.limit == "数役满" and v.base == 8000 and v.yakuman == 0
    v2 = value("11122233345699m", "9m", riichi=1, dora=6, config=RuleConfig(kazoe=False))
    assert v2.base == 6000 and v2.limit == "三倍满"


def test_tie_prefers_yakuman():
    """同一手牌的四暗刻和数役满都是 8000 基本点,记作四暗刻。"""
    v = value("11p05p5p999p777p666p", "9p", tsumo=True, riichi=1, dora=5)
    assert "四暗刻" in v.yakuman_names


# ---------------------------------------------------------------- 没役、宝牌


def test_no_yaku_returns_none():
    assert value("456p678s345s22p", "3s", melds=[chi("123m")], seat_wind=S) is None
    assert value("456p678s345s22p", "3s", melds=[chi("123m")], seat_wind=S, dora=3) is None  # 宝牌不是役


def test_dora_and_aka_are_counted():
    v = value("123m406p789s345s22p", "3s", riichi=1, dora=2, ura=1, seat_wind=S)
    assert dict(v.yaku)["赤宝牌"] == 1 and dict(v.yaku)["宝牌"] == 2 and dict(v.yaku)["里宝牌"] == 1
    assert v.han == 2 + 4


# ---------------------------------------------------------------- 符


@pytest.mark.parametrize(
    "hand,win,melds,ctx,fu",
    [
        ("123m456p789s234s55p", "5p", [], dict(riichi=1), 40),  # 20 + 门清荣和 10 + 单骑 2 = 32 → 40
        ("123m456p789s345s22p", "3s", [], dict(riichi=1), 30),  # 平和荣和
        ("123m456p789s345s22p", "3s", [], dict(tsumo=True), 20),  # 平和自摸
        ("123m456p789s345s22p", "4s", [], dict(tsumo=True), 30),  # 20 + 自摸 2 + 嵌张 2 = 24 → 30
        ("123m456p789s111z22p", "3m", [], dict(riichi=1), 40),  # 20 + 门清荣和 10 + 东暗刻 8 + 边张 2 = 40
        ("234m456p22p", "2p", [chi("678s"), pon("555p")], {}, 30),  # 20 + 明刻 2 + 单骑 2 = 24 → 30
        ("234m456p66p", "6p", [chi("789s"), pon("111z")], dict(seat_wind=0), 30),  # 20+4+2=26→30
        ("234m456p66p", "2m", [chi("678s"), chi("234s")], {}, 30),  # 副露平和形荣和: 30
        ("234m456p66p", "2m", [chi("678s"), chi("234s")], dict(tsumo=True), 30),  # 20 + 自摸 2 = 22 → 30
        ("234m456p66p", "2m", [chi("789s"), chi("123s")], {}, None),  # 没役
        ("234m66p555z", "5z", [chi("789s"), kan("9999p", MeldType.ANKAN)], {}, 60),  # 20+暗杠幺九32+明刻白4=56→60
        ("234m66p", "3m", [kan("1111z", MeldType.ANKAN), kan("5555z", MeldType.ANKAN), chi("789s")], dict(seat_wind=0), 90),
    ],
)
def test_fu(hand, win, melds, ctx, fu):
    ctx = dict(ctx)
    ctx.setdefault("seat_wind", S)
    v = value(hand, win, melds=melds, **ctx)
    if fu is None:
        assert v is None
    else:
        assert v is not None and v.fu == fu, (v.fu, v.yaku)


def test_fu_dragon_and_double_wind_pair():
    # 雀头是白 +2,中张暗刻 4,嵌张 2,门清荣和 10: 20+10+2+4+2 = 38 → 40
    assert value("123m444p789s123s55z", "2s", riichi=1, seat_wind=S).fu == 40
    # 连风雀头(东场东家的东)+4: 20+10+4+单骑2 = 36 → 40;平和不成立
    v = value("123m456p789s345s11z", "1z", riichi=1, seat_wind=0, round_wind=0)
    assert v.fu == 40 and "平和" not in names(v)


def test_shanpon_ron_minko():
    """双碰荣和: 荣和那组算明刻。中张明刻 2 + 幺九暗刻 8 + 门清荣和 10 + 20 = 40。"""
    v = value("123m456p999s777p55m", "7p", riichi=1, seat_wind=S)
    assert v.fu == 40


def test_ambiguous_wait_takes_higher_fu():
    """456p + 555p 和 5p: 看成嵌张(555p 算暗刻)比看成双碰多符,取 50 符。"""
    v = value("123m456p999s555p55m", "5p", riichi=1, seat_wind=S)
    assert v.fu == 50


# ---------------------------------------------------------------- 点数表


@pytest.mark.parametrize(
    "han,fu,non_dealer_ron,dealer_ron",
    [
        (1, 30, 1000, 1500),
        (1, 40, 1300, 2000),
        (2, 25, 1600, 2400),
        (2, 30, 2000, 2900),
        (3, 30, 3900, 5800),
        (3, 60, 7700, 11600),  # 不做切上满贯
        (4, 30, 7700, 11600),  # 不做切上满贯
        (3, 70, 8000, 12000),
        (4, 40, 8000, 12000),
        (5, 30, 8000, 12000),
        (6, 30, 12000, 18000),
        (7, 30, 12000, 18000),
        (8, 30, 16000, 24000),
        (10, 30, 16000, 24000),
        (11, 30, 24000, 36000),
        (12, 30, 24000, 36000),
        (13, 30, 32000, 48000),
        (1, 110, 3600, 5300),
    ],
)
def test_ron_table(han, fu, non_dealer_ron, dealer_ron):
    b = base_points(han, fu)
    assert ron_points(b, False) == non_dealer_ron
    assert ron_points(b, True) == dealer_ron


@pytest.mark.parametrize(
    "han,fu,child_pays,dealer_pays,dealer_win_each",
    [
        (1, 30, 300, 500, 500),
        (2, 20, 400, 700, 700),
        (3, 20, 700, 1300, 1300),
        (4, 20, 1300, 2600, 2600),
        (3, 30, 1000, 2000, 2000),
        (4, 30, 2000, 3900, 3900),
        (5, 30, 2000, 4000, 4000),
        (6, 30, 3000, 6000, 6000),
    ],
)
def test_tsumo_table(han, fu, child_pays, dealer_pays, dealer_win_each):
    b = base_points(han, fu)
    assert tsumo_points(b, False, False) == child_pays
    assert tsumo_points(b, False, True) == dealer_pays
    assert tsumo_points(b, True, False) == dealer_win_each


def test_limit_names():
    assert value("123m456p789s345s22p", "3s", riichi=1, dora=3, seat_wind=S).limit == "满贯"
    assert value("123m456p789s345s22p", "3s", riichi=1, dora=5, seat_wind=S).limit == "跳满"
    assert value("123m456p789s345s22p", "3s", riichi=1, dora=7, seat_wind=S).limit == "倍满"
    assert value("123m456p789s345s22p", "3s", riichi=1, dora=10, seat_wind=S).limit == "三倍满"

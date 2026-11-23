"""日麻: 牌的编号、动作编号、和牌型、听牌、向听数。"""
import random

import pytest

from riichi import actions as A
from riichi.actions import NUM_ACTIONS, Action, ActionType
from riichi.hand import decompose, is_agari, is_chiitoi, is_kokushi, waits
from riichi.shanten import discard_shanten, shanten, useful_tiles
from riichi.tiles import (
    dora_of,
    full_wall,
    hand_tiles,
    kind_of,
    parse_tile,
    parse_tiles,
    tile_name,
    tiles_str,
    tiles_to_counts,
)


def C(text):
    return tiles_to_counts(parse_tiles(text))


# ---------------------------------------------------------------- 牌


def test_full_wall_has_136_tiles_and_three_reds():
    wall = full_wall()
    assert len(wall) == 136
    assert tiles_to_counts(wall) == [4] * 34
    assert sorted(t for t in wall if t >= 34) == [34, 35, 36]
    assert not any(t >= 34 for t in full_wall(aka=False))


def test_parse_and_print():
    assert parse_tiles("19m0p5s1234567z") == [0, 8, 35, 22, 27, 28, 29, 30, 31, 32, 33]
    assert tiles_str(parse_tiles("5m0m3p7z")) == "05m3p7z"
    assert tile_name(parse_tile("0s")) == "赤5条"
    assert tile_name(parse_tile("6z")) == "发"
    assert kind_of(parse_tile("0p")) == kind_of(parse_tile("5p"))
    with pytest.raises(ValueError):
        parse_tiles("8z")


def test_hand_tiles_roundtrip():
    tiles = parse_tiles("055m123p406s11z")
    reds = [1, 0, 1]
    assert hand_tiles(tiles_to_counts(tiles), reds) == sorted(tiles, key=lambda t: (kind_of(t), -t))


@pytest.mark.parametrize(
    "indicator,dora",
    [("1m", "2m"), ("9m", "1m"), ("9p", "1p"), ("9s", "1s"), ("4z", "1z"), ("1z", "2z"), ("7z", "5z"), ("5z", "6z"), ("0m", "6m")],
)
def test_dora_of(indicator, dora):
    """宝牌是指示牌的下一张: 9 → 1,北 → 东,中 → 白。"""
    assert dora_of(kind_of(parse_tile(indicator))) == kind_of(parse_tile(dora))


# ---------------------------------------------------------------- 动作编号


def test_action_ids_roundtrip():
    assert NUM_ACTIONS == 119
    for i in range(NUM_ACTIONS):
        assert Action.from_id(i).id == i


def test_action_id_layout():
    """编号方案见 docs/riichi-rules.md 第 8 节。"""
    assert A.discard(0).id == 0 and A.discard(36).id == 36
    assert A.ankan(0).id == 37 and A.ankan(33).id == 70
    assert A.kakan(0).id == 71 and A.kakan(33).id == 104
    assert A.RIICHI.id == 105
    assert [A.chi(s, r).id for s in range(3) for r in (False, True)] == list(range(106, 112))
    assert A.pon(False).id == 112 and A.pon(True).id == 113
    assert (A.DAIMINKAN.id, A.TSUMO.id, A.RON.id, A.KYUUSHU.id, A.PASS.id) == (114, 115, 116, 117, 118)
    assert Action.from_id(110).type == ActionType.CHI


# ---------------------------------------------------------------- 和牌型


@pytest.mark.parametrize(
    "hand",
    ["123m456p789s11122z", "11122233344455m", "1122m3344p5566s77z", "19m19p19s12345677z", "234m234m234m55p678s"],
)
def test_agari_forms(hand):
    assert is_agari(C(hand))


@pytest.mark.parametrize("hand", ["123m456p789s11123z", "1122m3344p5566s7z1z", "11223344556677m"[:-1] + "8m"])
def test_not_agari(hand):
    assert not is_agari(C(hand))


def test_chiitoi_needs_seven_distinct_pairs():
    """4 张相同的牌不能当两个对子。"""
    assert is_chiitoi(C("1122m3344p5566s77z"))
    assert not is_chiitoi(C("1111m3344p5566s77z"))
    assert not is_agari(C("1111m3344p5566s77z"))


def test_kokushi():
    assert is_kokushi(C("19m19p19s12345677z"))
    assert not is_kokushi(C("19m19p19s1234566z") + [0])  # 少一种
    assert not is_agari(C("19m19p19s12345677z"), num_melds=1)  # 有副露时不算


def test_agari_with_melds():
    assert is_agari(C("123m55p"), num_melds=2)
    assert not is_agari(C("1122m3344p5566s77z"), num_melds=1)


def test_waits():
    assert waits(C("123m456p789s1112z")) == (28,)  # 字牌不能连: 只单骑南
    assert set(waits(C("123m456p789s23s11z"))) == {18, 21}  # 两面 1-4 条
    assert set(waits(C("1112345678999m"))) == set(range(9))  # 纯正九莲
    assert set(waits(C("19m19p19s1234567z"))) == set(kind_of(t) for t in parse_tiles("19m19p19s1234567z"))
    assert waits(C("123m456p789s1111z")) == ()  # 只听自己占满的第五张: 不算
    assert set(waits(C("2233m"), num_melds=3)) == {1, 2}  # 双碰


def test_decompose_lists_all_ways():
    decs = decompose(C("111222333m45699p"))
    assert len(decs) == 2  # 三个刻子 或 三个 123 顺子


# ---------------------------------------------------------------- 向听数


@pytest.mark.parametrize(
    "hand,expected",
    [
        ("123m456p789s1112z", 0),
        ("123m456p789s11122z", -1),
        ("123m456p789s1123z", 1),
        ("19m19p19s1234567z", 0),
        ("19m19p19s123456z5m", 1),
        ("1122m3344p5566s7z", 0),
        ("1357m1357p1357s1z", 4),  # 6 个嵌张搭子,只能用 4 个
        ("147m258p369s1234z", 6),  # 标准型 8、国士 7、七对子 6(13 种各一张)
        ("19m19p19s1234z55p", 3),  # 国士: 10 种幺九,没有对子 → 13 - 10 = 3
    ],
)
def test_shanten_examples(hand, expected):
    assert shanten(C(hand)) == expected


def test_shanten_matches_waits_on_random_hands():
    """随机 13 张: 向听数为 0 当且仅当 waits() 非空(只看形)。14 张: -1 当且仅当成和牌型。"""
    rng = random.Random(5)
    wall = [k for k in range(34) for _ in range(4)]
    for _ in range(3000):
        rng.shuffle(wall)
        c = tiles_to_counts(wall[:13])
        assert (shanten(c) == 0) == bool(waits(c))
        c14 = tiles_to_counts(wall[:14])
        assert (shanten(c14) == -1) == is_agari(c14)


def test_shanten_drops_by_at_most_one_per_tile():
    rng = random.Random(9)
    wall = [k for k in range(34) for _ in range(4)]
    for _ in range(500):
        rng.shuffle(wall)
        c = tiles_to_counts(wall[:13])
        s = shanten(c)
        good = set(useful_tiles(c))
        for k in range(34):
            if c[k] >= 4:
                continue
            c[k] += 1
            s2 = shanten(c)
            c[k] -= 1
            assert s2 in (s, s - 1)
            assert (s2 == s - 1) == (k in good)


def test_tenpai_with_melds():
    assert shanten(C("1234m"), num_melds=3) == 0
    assert shanten(C("1m"), num_melds=4) == 0


def test_discard_shanten_matches_direct_computation():
    """增量算法(只改一门)和直接重算的结果一致,含七对子、国士和有副露的情形。"""
    rng = random.Random(11)
    wall = [k for k in range(34) for _ in range(4)]
    for trial in range(2000):
        rng.shuffle(wall)
        melds = trial % 3 if trial % 5 else 0
        n = 14 - 3 * melds
        # 一部分手牌偏向幺九,好覆盖国士
        tiles = wall[:n] if trial % 4 else [k for k in wall if k in (0, 8, 9, 17, 18, 26) or k >= 27][:n]
        c = tiles_to_counts(tiles)
        got = discard_shanten(c, melds)
        for k, v in got.items():
            c[k] -= 1
            assert v == shanten(c, melds), (tiles, k)
            c[k] += 1

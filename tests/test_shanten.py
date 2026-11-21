import random

import pytest

from chuanma.hand import is_win, winning_tiles
from chuanma.shanten import shanten, useful_tiles
from chuanma.tiles import full_wall, parse_tiles, tiles_to_counts

from helpers import MAN, PIN, SOU


def c(text):
    return tiles_to_counts(parse_tiles(text))


@pytest.mark.parametrize(
    "hand, melds, void, expected",
    [
        ("123m456m789m123p55p", 0, SOU, -1),  # 已胡
        ("123m456m789m13p99p", 0, SOU, 0),  # 嵌张听
        ("123m456m789m1p99p5p", 0, SOU, 1),  # 一向听
        ("1112345678999m", 0, SOU, 0),  # 九莲宝灯听牌
        ("1133m5577m2244p6p", 0, SOU, 0),  # 七对听牌
        ("1133m5577m2244p66p", 0, SOU, -1),  # 七对胡
        ("1133m5577m24p68p9m", 0, SOU, 2),  # 四对,七对型二向听
        ("12345689m13579p", 0, SOU, 2),  # 两面子 + 三搭子,没有将
        ("55p", 4, SOU, -1),  # 四副露单吊已胡
        ("5p", 4, SOU, 0),  # 四副露单吊听牌
        ("123m45p99p", 2, SOU, 0),  # 两副露,两面听
        ("123m4p99p8p", 2, SOU, 1),  # 两副露,一向听
    ],
)
def test_known_shanten(hand, melds, void, expected):
    assert shanten(c(hand), melds, void) == expected


def test_void_tiles_are_dead_weight():
    # 同一手牌,缺的那门里的牌不算数
    hand = c("123m456m789m13p99p")
    assert shanten(hand, 0, SOU) == 0
    assert shanten(hand, 0, PIN) > 0  # 筒子全废,只剩 9 张万
    assert shanten(c("123m456m789m1359s"), 0, SOU) == shanten(c("123m456m789m"), 0, SOU)


def test_fourteen_tile_hand():
    # 14 张型: 打掉一张后最好能到的向听数
    assert shanten(c("123m456m789m13p99p5p"), 0, SOU) == 0
    assert shanten(c("123m456m789m123p55p"), 0, SOU) == -1


def test_useful_tiles_match_waits_when_tenpai():
    for text in ["123m456m789m13p99p", "123m456m789m23p99p", "1112345678999m", "1133m5577m2244p6p"]:
        hand = c(text)
        assert shanten(hand, 0, SOU) == 0
        assert useful_tiles(hand, 0, SOU) == winning_tiles(hand, 0, SOU)


def test_useful_tiles_one_shanten():
    # 123m456m789m + 1p 99p 5p: 进 2p/3p(配 1p)、3p-7p(配 5p)、9p 等都有用
    tiles = useful_tiles(c("123m456m789m1p99p5p"), 0, SOU)
    assert set(parse_tiles("2346p79p")) <= set(tiles) | set(parse_tiles("9p"))
    assert all(t // 9 != SOU for t in tiles)


def test_agrees_with_win_and_tenpai_on_random_hands():
    """随机牌: 向听数 -1 等价于胡牌,0 等价于听牌(存在能胡的牌)。"""
    rng = random.Random(1)
    wall = full_wall()
    checked_win = checked_ten = 0
    for _ in range(4000):
        void = rng.randrange(3)
        pool = [t for t in wall if t // 9 != void]
        hand14 = tiles_to_counts(rng.sample(pool, 14))
        assert (shanten(hand14, 0, void) == -1) == is_win(hand14, 0)
        checked_win += is_win(hand14, 0)
        hand13 = tiles_to_counts(rng.sample(pool, 13))
        s = shanten(hand13, 0, void)
        waits = [
            t
            for t in range(27)
            if t // 9 != void and hand13[t] < 4 and is_win(_plus(hand13, t), 0)
        ]
        if waits:
            assert s == 0
            checked_ten += 1
        else:
            assert s >= 0
            # 向听数为 0 却没有能胡的牌,只可能是听的牌自己已经拿满 4 张
            if s == 0:
                assert any(hand13[t] == 4 for t in range(27))
    assert checked_ten > 0


def test_structured_random_hands_shanten_decreases_to_win():
    """从一手胡牌里换掉 k 张牌,向听数不会超过 k - 1。"""
    rng = random.Random(2)
    base = parse_tiles("123m456m789m123p55p")
    for _ in range(500):
        k = rng.randint(1, 4)
        hand = list(base)
        rng.shuffle(hand)
        hand = hand[k:]
        while len(hand) < 14:
            t = rng.randrange(18)  # 只补万和筒
            if hand.count(t) < 4:
                hand.append(t)
        assert shanten(tiles_to_counts(hand), 0, SOU) <= k - 1


def _plus(counts, t):
    out = list(counts)
    out[t] += 1
    return out

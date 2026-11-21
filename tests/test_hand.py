import pytest

from chuanma.hand import is_seven_pairs, is_win, standard_decompositions, winning_tiles
from chuanma.tiles import parse_tiles, tiles_to_counts

from helpers import MAN, PIN, SOU


def c(text):
    return tiles_to_counts(parse_tiles(text))


@pytest.mark.parametrize(
    "hand",
    [
        "123m456m789m123p55p",  # 四顺子一对
        "111m222m333p444p55p",  # 四刻子一对
        "11123456789999m",  # 九莲宝灯型
        "11223344556677m",  # 既是七对也是标准型
        "1133m5577m2244p66p",  # 纯七对
        "1111m3355m2244p66p",  # 带四张的七对
        "223344m556677p99p",
    ],
)
def test_winning_hands(hand):
    assert is_win(c(hand), 0)


@pytest.mark.parametrize(
    "hand",
    [
        "123m456m789m123p59p",  # 没有将
        "123m456m789m124p55p",  # 差一张
        "1133m5577m2244p69p",  # 六对半
        "12345689m13579p1m",
    ],
)
def test_non_winning_hands(hand):
    assert not is_win(c(hand), 0)


def test_win_with_melds():
    # 副露两组后手里应剩 8 张
    assert is_win(c("123m456m55p"), 2)
    assert not is_win(c("123m456m55p"), 1)  # 张数对不上
    assert is_win(c("55p"), 4)
    # 七对必须门前清
    assert not is_win(c("1133m5577m"), 2)


def test_seven_pairs():
    assert is_seven_pairs(c("1133m5577m2244p66p"))
    assert is_seven_pairs(c("1111m3355m2244p66p"))
    assert not is_seven_pairs(c("111m3355m2244p666p"))


def test_decompositions():
    # 111222333m 既能拆成三个刻子,也能拆成三个顺子
    decs = set(standard_decompositions(c("111222333m55p")))
    shapes = {tuple(sorted(k for k, _ in melds)) for _, melds in decs}
    assert (True, True, True) in shapes
    assert (False, False, False) in shapes
    assert standard_decompositions(c("123m456m789m123p59p")) == []


def test_winning_tiles():
    # 九莲宝灯听全部九张万
    assert winning_tiles(c("1112345678999m"), 0, SOU) == list(range(9))
    # 嵌张
    assert winning_tiles(c("123m456m789m13p99p"), 0, SOU) == parse_tiles("2p")
    # 两面
    assert winning_tiles(c("123m456m789m23p99p"), 0, SOU) == parse_tiles("14p")
    # 没听
    assert winning_tiles(c("12345689m13579p"), 0, SOU) == []


def test_winning_tiles_respects_void():
    # 手里还有缺门牌: 不算听牌
    assert winning_tiles(c("123m456m789m13p99p"), 0, PIN) == []
    # 听的牌恰好是缺门: 不能算
    assert winning_tiles(c("123m456m789m23p99p"), 0, MAN) == []


def test_winning_tiles_skips_exhausted_tile():
    # 手里 4 张 5 万,理论上还能"听"5 万(4455m 型),但第五张不存在
    hand = c("5555m46m123p456p9p")
    waits = winning_tiles(hand, 0, SOU)
    assert parse_tiles("5m")[0] not in waits
    # 已经碰了 9 筒又单吊 9 筒... 手里 1 张 + 碰 3 张 = 4 张,同样不算
    hand = c("123m456m789m9p")
    assert winning_tiles(hand, 1, SOU, meld_tiles=parse_tiles("999p")) == []

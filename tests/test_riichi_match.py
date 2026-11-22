"""日麻: 一整场(半庄)的推进和终局。规则见 docs/riichi-rules.md 第 2、5.4 节。

直接调用 _finish_hand(一局结束时的统一出口)来摆出各种局况,不用真的打到那一局。
"""
import pytest

from riichi import Game, RuleConfig
from riichi import actions as A

from riichi_helpers import J1, J2, J3, TENPAI, act, position, tsumogiri


def at(round_wind, kyoku, scores, honba=0, sticks=0, config=None):
    g = Game(config=config or RuleConfig(), seed=3)
    g.round_wind, g.kyoku, g.dealer = round_wind, kyoku, kyoku
    g.honba, g.sticks = honba, sticks
    g.scores = list(scores)
    return g


def end_hand(g, renchan, next_honba=None):
    if next_honba is None:
        next_honba = g.honba + 1 if renchan else 0
    g._finish_hand({"type": "test"}, list(g.scores), renchan=renchan, next_honba=next_honba)


def test_dealer_rotates_on_non_dealer_win():
    g = at(0, 0, [25000] * 4, honba=2)
    end_hand(g, renchan=False)
    assert (g.round_wind, g.kyoku, g.dealer, g.honba) == (0, 1, 1, 0)


def test_renchan_keeps_dealer_and_adds_honba():
    g = at(0, 2, [25000] * 4, honba=1)
    end_hand(g, renchan=True)
    assert (g.round_wind, g.kyoku, g.dealer, g.honba) == (0, 2, 2, 2)


def test_east_4_goes_to_south_1():
    g = at(0, 3, [25000] * 4)
    end_hand(g, renchan=False)
    assert (g.round_wind, g.kyoku, g.dealer) == (1, 0, 0)
    assert not g.is_over


def test_south_4_ends_when_someone_reaches_30000():
    g = at(1, 3, [31000, 25000, 24000, 20000])
    end_hand(g, renchan=False)
    assert g.is_over and g.end_reason == "finished"


def test_south_4_without_30000_enters_west():
    g = at(1, 3, [29000, 27000, 24000, 20000])
    end_hand(g, renchan=False)
    assert not g.is_over and (g.round_wind, g.kyoku, g.dealer) == (2, 0, 0)


def test_west_ends_as_soon_as_someone_reaches_30000():
    g = at(2, 1, [30000, 27000, 23000, 20000])
    end_hand(g, renchan=True)
    assert g.is_over and g.end_reason == "overtime_target"


def test_west_4_is_the_last_hand():
    g = at(2, 3, [29000, 27000, 24000, 20000])
    end_hand(g, renchan=False)
    assert g.is_over and g.end_reason == "overtime_over"


def test_dealer_top_stops_at_all_last():
    """南 4 局庄家连庄,而且是第一名且到 30000: 结束(庄家止和)。"""
    g = at(1, 3, [20000, 25000, 24000, 31000])
    end_hand(g, renchan=True)
    assert g.is_over and g.end_reason == "dealer_top"


def test_dealer_renchan_continues_when_not_top():
    g = at(1, 3, [32000, 25000, 24000, 19000])
    end_hand(g, renchan=True)
    assert not g.is_over and (g.kyoku, g.dealer, g.honba) == (3, 3, 1)


@pytest.mark.parametrize("low,over", [(-100, True), (0, False)])
def test_tobi(low, over):
    g = at(0, 0, [50100, 25000, 25000 - 0, low + 0])
    g.scores = [100000 - 50000 - low, 25000, 25000, low]
    end_hand(g, renchan=False)
    assert g.is_over == over
    if over:
        assert g.end_reason == "tobi"


def test_tobi_switch():
    g = at(0, 0, [50100, 25000, 25000, -100], config=RuleConfig(tobi=False))
    end_hand(g, renchan=False)
    assert not g.is_over


def test_tonpu_ends_after_east_4():
    g = at(0, 3, [31000, 25000, 24000, 20000], config=RuleConfig(length="tonpu"))
    end_hand(g, renchan=False)
    assert g.is_over
    g = at(0, 3, [29000, 27000, 24000, 20000], config=RuleConfig(length="tonpu"))
    end_hand(g, renchan=False)
    assert not g.is_over and g.round_wind == 1  # 东风战的延长是南场


def test_leftover_sticks_go_to_top():
    g = at(1, 3, [30000, 26000, 23000, 19000], sticks=2)
    end_hand(g, renchan=False)
    assert g.is_over and g.scores == [32000, 26000, 23000, 19000] and g.sticks == 0


def test_ranks_tie_broken_by_seat():
    g = at(0, 0, [25000, 25000, 30000, 20000])
    assert g.ranks() == [1, 2, 0, 3]


def test_final_points():
    g = at(1, 3, [40000, 30000, 20000, 10000])
    end_hand(g, renchan=False)
    assert g.final_points() == [50.0, 10.0, -20.0, -40.0]  # (点 − 30000)/1000 + 马,一位再 +20
    assert sum(g.final_points()) == 0
    assert g.result()["ranks"] == [0, 1, 2, 3]


def test_custom_uma():
    g = at(1, 3, [40000, 30000, 20000, 10000], config=RuleConfig(uma=(30, 10, -10, -30)))
    end_hand(g, renchan=False)
    assert g.final_points() == [60.0, 10.0, -20.0, -50.0]


def test_win_by_dealer_is_renchan_and_honba_counts():
    g = position([TENPAI + "8m", J1, J2, J3], drawn="8m", draws="9m9p1p1s", config=RuleConfig())  # 9s 会被庄家吃
    g.honba = 1
    act(g, 0, "8m")
    for s in (1, 2, 3):
        tsumogiri(g, s)
    act(g, 0, A.TSUMO)
    r = g.hand_results[-1]
    assert r["renchan"] and g.dealer == 0 and g.honba == 2
    # 庄家 门前清自摸和 + 平和 2 番 20 符: 每家 700,一本场每家再 +100
    assert r["deltas"] == [2400, -800, -800, -800]


def test_win_by_non_dealer_resets_honba():
    g = position([J1 + "9m", TENPAI, J2, J3], drawn="9m", draws="1s", config=RuleConfig())
    g.honba = 3
    tsumogiri(g, 0)
    act(g, 1, A.TSUMO)
    assert g.dealer == 1 and g.honba == 0 and g.kyoku == 1


def test_points_conserved_including_sticks():
    g = position([TENPAI + "1z", J1, J2, J3], drawn="1z", draws="9m9p9s1s", config=RuleConfig())
    act(g, 0, A.RIICHI)
    act(g, 0, "1z")
    assert sum(g.scores) + 1000 * g.sticks == 100000
    for s in (1, 2, 3):
        tsumogiri(g, s)
    act(g, 0, A.TSUMO)
    assert sum(g.scores) == 100000 and g.sticks == 0

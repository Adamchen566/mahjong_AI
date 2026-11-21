import pytest

from chuanma import MeldType, RuleConfig, WinContext, evaluate_fan
from chuanma.fan import best_ting
from chuanma.tiles import parse_tiles, tiles_to_counts

from helpers import SOU, gang, pong

# 关掉门清/中张,方便单独验证牌型番
PLAIN = RuleConfig(men_qing_zhong_zhang=False)
RON = WinContext(zimo=False)


def fan(hand, melds=(), ctx=RON, config=PLAIN):
    return evaluate_fan(tiles_to_counts(parse_tiles(hand)), list(melds), ctx, config)


@pytest.mark.parametrize(
    "hand, melds, expected_fan, expected_names",
    [
        ("123m456m789m123p55p", (), 0, ("平胡",)),
        ("111m222m333p444p55p", (), 1, ("对对胡",)),
        ("123m456m789m123m55m", (), 2, ("平胡", "清一色")),
        ("1133m5577m2244p66p", (), 2, ("七对",)),
        ("1111m3355m2244p66p", (), 3, ("龙七对",)),
        ("1111m3333m2244p66p", (), 4, ("龙七对", "根×1")),
        ("11223344556677m", (), 4, ("七对", "清一色")),
        ("11112233556677m", (), 5, ("龙七对", "清一色")),
        ("123m789m123p999p11p", (), 2, ("带幺九",)),
        ("222m555m888m222p55p", (), 3, ("将对",)),
        ("111m999m111p999p11s", (), 3, ("对对胡", "带幺九")),
        ("111m222m333m444m55m", (), 3, ("对对胡", "清一色")),
        # 手里三张 + 顺子里一张 = 一根
        ("555m567m123p456p99p", (), 1, ("平胡", "根×1")),
    ],
)
def test_pattern_fans(hand, melds, expected_fan, expected_names):
    result = fan(hand, melds)
    assert result.fan == expected_fan
    assert result.names == expected_names
    assert result.points == 2**expected_fan


def test_gen_from_pong_plus_hand_tile():
    result = fan("567m123p456p99p", [pong("5m")])
    assert (result.fan, result.names) == (1, ("平胡", "根×1"))


def test_gen_from_gang():
    result = fan("123m456m789m55p", [gang("9p")])
    assert (result.fan, result.names) == (1, ("平胡", "根×1"))


def test_jin_gou_diao():
    melds = [pong("1m"), pong("2p"), pong("3p"), pong("9p")]
    result = fan("55m", melds)
    assert (result.fan, result.names) == (2, ("对对胡", "金钩钓"))


def test_shi_ba_luo_han_is_capped():
    melds = [gang("1m"), gang("2p"), gang("3p"), gang("9p")]
    result = fan("55m", melds)
    assert result.names == ("对对胡", "金钩钓", "根×4")
    assert result.fan == 6
    assert result.capped_fan == 5
    assert result.points == 32
    assert fan("55m", melds, config=RuleConfig(men_qing_zhong_zhang=False, max_fan=8)).points == 64


def test_dai_yao_jiu_needs_terminal_melds():
    assert fan("123m789m11p", [pong("9p"), pong("9s")]).names == ("带幺九",)
    assert fan("123m789m11p", [pong("9p"), pong("5m")]).names == ("平胡",)


def test_men_qing_and_zhong_zhang():
    default = RuleConfig()
    assert fan("234m456m678m234p55p", config=default).names == ("平胡", "门清", "中张")
    assert fan("234m456m678m234p55p", config=default).fan == 2
    # 碰过就不是门清
    assert fan("234m456m678m55p", [pong("3p")], config=default).names == ("平胡", "中张")
    # 暗杠不破门清
    r = fan("123m456m789m55p", [gang("3p", MeldType.AN_GANG)], config=default)
    assert r.names == ("平胡", "根×1", "门清")
    # 七对本来就必须门清,不再另算
    assert fan("2233m5577m2244p66p", config=default).names == ("七对", "中张")


def test_context_bonuses():
    hand = "123m456m789m123p55p"
    assert fan(hand, ctx=WinContext(zimo=True, tianhu=True)).fan == 5
    assert fan(hand, ctx=WinContext(zimo=False, dihu=True)).names == ("平胡", "地胡")
    assert fan(hand, ctx=WinContext(zimo=True, gang_shang_hua=True)).names == ("平胡", "杠上花")
    assert fan(hand, ctx=WinContext(zimo=False, gang_shang_pao=True)).names == ("平胡", "杠上炮")
    assert fan(hand, ctx=WinContext(zimo=False, qiang_gang=True)).names == ("平胡", "抢杠胡")
    assert fan(hand, ctx=WinContext(zimo=True, haidi=True)).names == ("平胡", "海底捞月")
    assert fan(hand, ctx=WinContext(zimo=False, haidi=True)).names == ("平胡", "海底炮")


def test_context_bonuses_can_be_disabled():
    hand = "123m456m789m123p55p"
    cfg = RuleConfig(men_qing_zhong_zhang=False, tian_di_hu=False, haidi=False)
    assert fan(hand, ctx=WinContext(zimo=True, tianhu=True, haidi=True), config=cfg).fan == 0


def test_zimo_jia_fan():
    hand = "123m456m789m123p55p"
    cfg = RuleConfig(men_qing_zhong_zhang=False, zimo_mode="jia_fan")
    assert fan(hand, ctx=WinContext(zimo=True), config=cfg).names == ("平胡", "自摸")
    assert fan(hand, ctx=WinContext(zimo=False), config=cfg).fan == 0
    # 默认的自摸加底不改变番数
    assert fan(hand, ctx=WinContext(zimo=True)).fan == 0


def test_not_a_win_raises():
    with pytest.raises(ValueError):
        fan("123m456m789m123p59p")


def test_best_ting_picks_highest_value_wait():
    # 23m 两面听: 胡 1 万只是平胡,胡 4 万是中张(全手无幺九)
    counts = tiles_to_counts(parse_tiles("23m456m678m234p55p"))
    tile, result = best_ting(counts, [], SOU, RuleConfig())
    assert tile == parse_tiles("4m")[0]
    assert result.names == ("平胡", "门清", "中张")
    assert best_ting(tiles_to_counts(parse_tiles("12345689m13579p")), [], SOU, RuleConfig()) is None

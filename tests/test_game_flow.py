"""逐条验证规则: 每个测试摆一个局面,走几步,检查合法动作和分数。

默认配置: 底分 1,自摸加底,计门清/中张,封顶 5 番。
"""
import pytest

from chuanma import Game, IllegalAction, MeldType, Phase, RuleConfig
from chuanma.actions import HU, MING_GANG, PASS, PONG, ActionType, an_gang, choose_void, discard, jia_gang
from chuanma.tiles import parse_tile, parse_tiles

from helpers import JUNK, MAN, PIN, SOU, build_wall, make_game, pong

T = parse_tile
WIN14 = "123m456m789m123p55p"  # 平胡(有幺九,门清)
WAIT_2P = "123m456m789m13p99p"  # 嵌张听 2 筒
WAIT_5P = "123m456m789m46p11p"  # 嵌张听 5 筒


def types(game):
    return {a.type for a in game.legal_actions()}


# ---------------------------------------------------------------- 自摸 / 点炮


def test_zimo_everyone_pays_with_jia_di():
    g = make_game([WIN14, JUNK, JUNK, JUNK], wall="9m9m")
    assert HU in g.legal_actions()
    g.step(HU)
    # 平胡 + 门清 = 1 番 = 2 分,自摸加底每家再付 1
    assert g.scores == [9, -3, -3, -3]
    assert g.won == [True, False, False, False]
    assert g.wins[0].zimo and g.wins[0].names == ("平胡", "门清")
    # 胡牌者离场,下家继续摸牌
    assert (g.phase, g.current) == (Phase.TURN, 1)


def test_zimo_modes():
    for mode, expected in (("none", 2), ("jia_di", 3), ("jia_fan", 4)):
        g = make_game([WIN14, JUNK, JUNK, JUNK], wall="9m", config=RuleConfig(zimo_mode=mode))
        g.step(HU)
        assert g.scores == [3 * expected, -expected, -expected, -expected]


def test_winner_can_decline_and_discard():
    g = make_game([WIN14, JUNK, JUNK, JUNK], wall="9m9m")
    g.step(discard(T("5p")))
    assert not g.won[0]
    assert g.current == 1


def test_ron_only_discarder_pays():
    g = make_game([JUNK + "2p", WAIT_2P, JUNK, JUNK], wall="9m9m")
    g.step(discard(T("2p")))
    assert (g.phase, g.current) == (Phase.RESPONSE, 1)
    assert g.legal_actions() == [HU, PASS]
    g.step(HU)
    assert g.scores == [-2, 2, 0, 0]
    assert g.wins[0].from_seat == 0 and not g.wins[0].zimo
    assert g.current == 2  # 胡牌者的下家摸牌


def test_multiple_ron_all_win():
    g = make_game([JUNK + "2p", WAIT_2P, WAIT_2P, JUNK], wall="9m9m")
    g.step(discard(T("2p")))
    assert g.current == 1
    g.step(HU)
    assert g.current == 2  # 还要问第二个能胡的人
    g.step(HU)
    assert g.scores == [-4, 2, 2, 0]
    assert g.won == [False, True, True, False]
    assert g.current == 3  # 最后一位胡牌者的下家


def test_ron_can_be_passed():
    g = make_game([JUNK + "2p", WAIT_2P, WAIT_2P, JUNK], wall="9m9m")
    g.step(discard(T("2p")))
    g.step(PASS)
    g.step(HU)
    assert g.won == [False, False, True, False]
    assert g.scores == [-2, 0, 2, 0]
    assert g.current == 3

    g = make_game([JUNK + "2p", WAIT_2P, WAIT_2P, JUNK], wall="9m9m")
    g.step(discard(T("2p")))
    g.step(PASS)
    g.step(PASS)
    assert not any(g.won)
    assert (g.phase, g.current) == (Phase.TURN, 1)


def test_hu_beats_pong():
    # 南家能碰 2 筒,西家能胡 2 筒: 南家选碰也没用
    pong_hand = "123456m13579p22p"
    g = make_game([JUNK + "2p", pong_hand, WAIT_2P, JUNK], wall="9m9m")
    g.step(discard(T("2p")))
    assert (g.current, g.legal_actions()) == (1, [PONG, PASS])
    g.step(PONG)
    g.step(HU)
    assert g.won == [False, False, True, False]
    assert g.melds[1] == []
    assert g.current == 3


def test_three_wins_end_the_game():
    g = make_game([WIN14, JUNK, JUNK, JUNK], wall="9m9m")
    g.won = [False, False, True, True]  # 假设西、北已经胡了
    g.step(HU)
    assert g.is_over and g.end_reason == "three_won"
    assert g.scores == [3, -3, 0, 0]  # 只有还没胡的南家付分
    assert g.legal_actions() == []
    with pytest.raises(IllegalAction):
        g.step(PASS)


# ---------------------------------------------------------------- 碰 / 杠


def test_pong_then_must_discard():
    hand1 = "123456m13579p22p"
    g = make_game([JUNK + "2p", hand1, JUNK, JUNK], wall="9m9m")
    g.step(discard(T("2p")))
    g.step(PONG)
    assert g.melds[1] == [pong("2p", from_seat=0)]
    assert g.discards[0] == []  # 被碰走的牌离开弃牌区
    assert (g.phase, g.current) == (Phase.TURN, 1)
    assert types(g) == {ActionType.DISCARD}  # 碰后只能出牌
    assert g.wall_remaining == 2  # 碰牌不摸牌


def test_ming_gang_pays_and_gang_shang_hua():
    hand1 = "555p123m456m789m1p"
    g = make_game([JUNK + "5p", hand1, JUNK, JUNK], wall="1p9m")
    g.step(discard(T("5p")))
    assert g.legal_actions() == [PONG, MING_GANG, PASS]
    g.step(MING_GANG)
    assert g.melds[1][0].type == MeldType.MING_GANG
    assert g.scores == [-2, 2, 0, 0]  # 放杠者一人付 2
    assert (g.current, g.drawn, g.after_gang) == (1, T("1p"), True)
    g.step(HU)
    # 平胡 + 一根 + 杠上花 = 2 番 = 4 分,自摸加底 5
    assert g.wins[0].names == ("平胡", "根×1", "杠上花")
    assert g.scores == [-7, 17, -5, -5]


def test_an_gang_everyone_pays():
    g = make_game(["5555p123m456m789m1p", JUNK, JUNK, JUNK], wall="9m9m")
    assert an_gang(T("5p")) in g.legal_actions()
    g.step(an_gang(T("5p")))
    assert g.scores == [6, -2, -2, -2]
    assert (g.current, g.drawn, g.after_gang) == (0, T("9m"), True)


def test_finished_players_do_not_pay_gang():
    g = make_game(["5555p123m456m789m1p", JUNK, JUNK, JUNK], wall="9m9m")
    g.won[2] = True
    g.step(an_gang(T("5p")))
    assert g.scores == [4, -2, 0, -2]


def test_jia_gang_completes_when_not_robbed():
    g = make_game(["5p123m456m789m1p", JUNK, JUNK, JUNK], wall="9m9m", melds=[[pong("5p", 1)], [], [], []])
    assert jia_gang(T("5p")) in g.legal_actions()
    g.step(jia_gang(T("5p")))
    assert g.melds[0][0].type == MeldType.JIA_GANG
    assert g.scores == [3, -1, -1, -1]
    assert (g.current, g.after_gang) == (0, True)


def test_rob_kong():
    g = make_game(["5p123m456m789m1p", WAIT_5P, JUNK, JUNK], wall="9m9m", melds=[[pong("5p", 1)], [], [], []])
    g.step(jia_gang(T("5p")))
    assert (g.phase, g.current) == (Phase.ROB_KONG, 1)
    assert g.legal_actions() == [HU, PASS]
    g.step(HU)
    # 平胡 + 门清 + 抢杠胡 = 2 番,被抢的人按点炮付;杠不成立,没有杠分
    assert g.wins[0].names == ("平胡", "门清", "抢杠胡")
    assert g.scores == [-4, 4, 0, 0]
    assert g.melds[0][0].type == MeldType.PONG
    assert g.current == 2


def test_rob_kong_declined():
    g = make_game(["5p123m456m789m1p", WAIT_5P, JUNK, JUNK], wall="9m9m", melds=[[pong("5p", 1)], [], [], []])
    g.step(jia_gang(T("5p")))
    g.step(PASS)
    assert g.melds[0][0].type == MeldType.JIA_GANG
    assert g.scores == [3, -1, -1, -1]
    assert (g.phase, g.current) == (Phase.TURN, 0)


def test_gang_shang_pao():
    g = make_game(["5555p12345689m9p", WAIT_2P, JUNK, JUNK], wall="2p9m")
    g.step(an_gang(T("5p")))
    g.step(discard(T("2p")))
    g.step(HU)
    assert g.wins[0].names == ("平胡", "门清", "杠上炮")
    # 东: 暗杠收 6,点炮付 4;南: 付杠 2,胡牌收 4
    assert g.scores == [2, 2, -2, -2]


def test_no_gang_when_wall_is_empty():
    g = make_game(["5555p123m456m789m1p", JUNK, JUNK, JUNK], wall="")
    assert ActionType.AN_GANG not in types(g)


# ---------------------------------------------------------------- 缺门


def test_must_discard_void_suit_first():
    g = make_game([WIN14, JUNK, JUNK, JUNK], wall="9m", voids=(MAN, SOU, SOU, SOU))
    # 手里还有缺门(万)时不能胡,只能打万
    assert types(g) == {ActionType.DISCARD}
    assert {a.tile for a in g.legal_actions()} == set(parse_tiles("123456789m"))


def test_cannot_claim_void_suit_tile():
    hand1 = "123456m13579p22p"
    g = make_game([JUNK + "2p", hand1, JUNK, JUNK], wall="9m9m", voids=(SOU, PIN, SOU, SOU))
    g.step(discard(T("2p")))
    # 南家缺筒: 不能碰 2 筒,直接轮到他摸牌
    assert (g.phase, g.current) == (Phase.TURN, 1)


def test_cannot_ron_with_void_tiles_in_hand():
    g = make_game([JUNK + "2p", WAIT_2P, JUNK, JUNK], wall="9m9m", voids=(SOU, MAN, SOU, SOU))
    g.step(discard(T("2p")))
    assert (g.phase, g.current) == (Phase.TURN, 1)


# ---------------------------------------------------------------- 海底 / 流局


def test_haidi_zimo():
    g = make_game([JUNK + "7m", WAIT_2P, JUNK, JUNK], wall="2p")
    g.step(discard(T("7m")))
    assert (g.phase, g.current, g.wall_remaining) == (Phase.TURN, 1, 0)
    g.step(HU)
    assert g.wins[0].names == ("平胡", "门清", "海底捞月")


def test_haidi_pao_and_no_pong_on_last_discard():
    hand2 = "123456m13579p22p"
    g = make_game([JUNK + "2p", WAIT_2P, hand2, JUNK], wall="")
    g.step(discard(T("2p")))
    # 最后一张弃牌: 西家有一对 2 筒也不能碰,只问能胡的南家
    assert (g.phase, g.current) == (Phase.RESPONSE, 1)
    g.step(HU)
    assert g.wins[0].names == ("平胡", "门清", "海底炮")
    assert g.current == 2 or g.is_over


def test_wall_exhausted_ends_game():
    g = make_game([JUNK + "9p", JUNK, JUNK, JUNK], wall="")
    g.step(discard(T("9p")))
    assert g.is_over and g.end_reason == "wall_exhausted"
    assert g.scores == [0, 0, 0, 0]  # 四家都没听,互不赔付


def test_draw_settlement_hua_zhu_da_jiao_tui_shui():
    # 东: 听牌(平胡+门清 = 2 分);南: 没听且收过杠分;西: 花猪(缺万但手里有万);北: 已胡
    g = make_game(
        [WAIT_2P + "7p", JUNK, JUNK, JUNK],
        wall="",
        voids=(SOU, SOU, MAN, SOU),
    )
    g.won[3] = True
    g._transfer("gang", 0, 1, 2, "暗杠")
    assert g.scores == [-2, 2, 0, 0]
    g.step(discard(T("7p")))
    assert g.end_reason == "wall_exhausted"
    by_kind = {}
    for t in g.transfers:
        by_kind.setdefault(t.kind, []).append((t.payer, t.payee, t.amount))
    assert sorted(by_kind["hua_zhu"]) == [(2, 0, 32), (2, 1, 32)]  # 花猪赔封顶给每个非花猪
    assert by_kind["da_jiao"] == [(1, 0, 2)]  # 无叫赔给有叫
    assert by_kind["tui_shui"] == [(1, 0, 2)]  # 无叫退回杠分
    assert g.scores == [34, 30, -64, 0]
    assert sum(g.scores) == 0


def test_draw_settlement_switches():
    cfg = RuleConfig(cha_hua_zhu=False, cha_da_jiao=False, tui_shui=False)
    g = make_game([WAIT_2P + "7p", JUNK, JUNK, JUNK], wall="", voids=(SOU, SOU, MAN, SOU), config=cfg)
    g._transfer("gang", 0, 1, 2, "暗杠")
    g.step(discard(T("7p")))
    assert g.scores == [-2, 2, 0, 0]


def test_tenpai_player_keeps_gang_score():
    g = make_game([JUNK + "7p", WAIT_2P, JUNK, JUNK], wall="")
    g._transfer("gang", 0, 1, 2, "暗杠")
    g.step(discard(T("7p")))
    # 南听牌: 不退税,还向没听的东、西、北各收 2
    assert [t.kind for t in g.transfers].count("tui_shui") == 0
    assert g.scores == [-4, 8, -2, -2]


# ---------------------------------------------------------------- 开局流程


# 用真实牌墙开局时,四家的牌合起来每种不能超过 4 张,所以另备几手带条子的废牌
JUNK_A = "1357m2468p13579s"
JUNK_B = "2468m1379p24689s"
JUNK_C = "1357m2468p12468s"


def start(hands, dealer_extra, draws="", **kw):
    cfg = RuleConfig(exchange_three=False)
    g = Game(config=cfg, wall=build_wall(hands, dealer_extra, draws), **kw)
    for seat in range(4):
        assert (g.phase, g.current) == (Phase.CHOOSE_VOID, seat)
        g.step(choose_void(SOU))
    return g


def test_tianhu():
    g = start(["123m456m789m123p5p", JUNK_A, JUNK_B, JUNK_C], "5p")
    assert (g.phase, g.current, g.drawn) == (Phase.TURN, 0, None)
    g.step(HU)
    # 平胡 + 门清 + 天胡 = 6 番,封顶 5 番 = 32 分,自摸加底 33
    assert g.wins[0].names == ("平胡", "门清", "天胡")
    assert g.wins[0].tile is None
    assert (g.wins[0].fan, g.wins[0].capped_fan) == (6, 5)
    assert g.scores == [99, -33, -33, -33]


def test_dihu_on_dealers_first_discard():
    g = start([JUNK, WAIT_2P, JUNK_A, JUNK_B], "2p")
    g.step(discard(T("2p")))
    g.step(HU)
    assert g.wins[0].names == ("平胡", "门清", "地胡")
    assert g.scores == [-32, 32, 0, 0]


def test_no_dihu_after_a_meld():
    g = start([JUNK, WAIT_2P, JUNK_A, JUNK_B], "2p")
    g.any_meld = True
    g.step(discard(T("2p")))
    g.step(HU)
    assert g.wins[0].names == ("平胡", "门清")


def test_deal_and_first_turn():
    g = Game(config=RuleConfig(exchange_three=False), seed=7, dealer=2)
    assert [sum(h) for h in g.hands] == [13, 13, 14, 13]
    assert g.wall_remaining == 55
    order = []
    while g.phase == Phase.CHOOSE_VOID:
        order.append(g.current)
        g.step(choose_void(MAN))
    assert order == [2, 3, 0, 1]  # 从庄家开始
    assert (g.phase, g.current) == (Phase.TURN, 2)


def test_exchange_three():
    g = Game(seed=11, exchange_direction=1)
    before = [g.hand_tiles(s) for s in range(4)]
    for seat in range(4):
        suit = None
        for pick in range(3):
            assert (g.phase, g.current) == (Phase.EXCHANGE, seat)
            legal = g.legal_actions()
            assert all(a.type == ActionType.EXCHANGE for a in legal)
            if suit is not None:  # 后两张必须和第一张同花色
                assert {a.tile // 9 for a in legal} == {suit}
            g.step(legal[0])
            suit = legal[0].tile // 9
    assert g.phase == Phase.CHOOSE_VOID
    assert [sum(h) for h in g.hands] == [14, 13, 13, 13]
    for seat in range(4):
        # 方向 1: 给下家
        assert g.exchange_in[(seat + 1) % 4] == g.exchange_out[seat]
        expected = list(before[seat])
        for t in g.exchange_out[seat]:
            expected.remove(t)
        expected += g.exchange_in[seat]
        assert sorted(expected) == g.hand_tiles(seat)


def test_bad_arguments():
    with pytest.raises(ValueError):
        Game(dealer=4)
    with pytest.raises(ValueError):
        Game(wall=[0] * 108)
    with pytest.raises(ValueError):
        Game(exchange_direction=0)
    with pytest.raises(ValueError):
        RuleConfig(zimo_mode="oops")


def test_illegal_action_leaves_state_untouched():
    g = make_game([JUNK + "2p", JUNK, JUNK, JUNK], wall="9m9m")
    with pytest.raises(IllegalAction):
        g.step(HU)
    with pytest.raises(IllegalAction):
        g.step(discard(T("9s")))
    assert g.history == []
    assert (g.phase, g.current) == (Phase.TURN, 0)
    g.step(discard(T("2p")).id)  # 也接受整数编号
    assert g.history == [discard(T("2p")).id]


# ---------------------------------------------------------------- 视图


def test_observation_hides_private_information():
    g = Game(config=RuleConfig(exchange_three=False), seed=3)
    g.step(choose_void(PIN))
    # 东家定了缺,但其他人还没定完: 南家看不到
    assert g.observation(1)["void"] == [None, None, None, None]
    assert g.observation(0)["void"] == [PIN, None, None, None]
    for _ in range(3):
        g.step(choose_void(SOU))
    obs = g.observation(1)
    assert obs["void"] == [PIN, SOU, SOU, SOU]
    assert obs["hand"] == g.hand_tiles(1)
    assert "hands" not in obs
    assert obs["legal_actions"] == []  # 没轮到南家
    assert g.observation(0)["legal_actions"] == g.legal_action_ids()
    assert obs["hand_sizes"] == [14, 13, 13, 13]


def test_observation_hides_others_an_gang_and_draws():
    g = make_game(["5555p123m456m789m1p", JUNK, JUNK, JUNK], wall="9m9m")
    g.step(an_gang(T("5p")))
    assert g.observation(0)["melds"][0][0]["tile"] == T("5p")
    assert g.observation(1)["melds"][0][0] == {"type": "AN_GANG", "tile": None, "from_seat": 0}
    assert g.observation(0)["drawn"] == T("9m")
    assert g.observation(1)["drawn"] is None
    draws = [e for e in g.events_for(1) if e["type"] == "draw"]
    assert draws and all(e["tile"] is None for e in draws)
    assert [e["tile"] for e in g.events_for(0) if e["type"] == "draw"] == [T("9m")]


def test_observation_reveals_everything_at_end():
    g = make_game([JUNK + "9p", JUNK, JUNK, JUNK], wall="")
    g.step(discard(T("9p")))
    obs = g.observation(1)
    assert obs["hands"] == [g.hand_tiles(s) for s in range(4)]
    assert obs["end_reason"] == "wall_exhausted"

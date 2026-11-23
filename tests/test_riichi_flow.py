"""日麻: 一局里的每一条流程规则。规则见 docs/riichi-rules.md 第 3 节。

局面用 position() 直接摆出来;J1/J2/J3 是吃碰不到、离听牌很远的废牌,TENPAI 听 1s/4s。
"""
import pytest

from riichi import IllegalAction, Phase, RuleConfig
from riichi import actions as A
from riichi.game import LIVE_END
from riichi.scoring import MeldType
from riichi.tiles import parse_tile

from riichi_helpers import J1, J2, J3, TENPAI, act, chi, last_wins, legal, make, pon, position, tsumogiri

HANCHAN = RuleConfig()


def yaku_names(win):
    return {n.split(" ")[0] for n, _ in win["yaku"]}


# ---------------------------------------------------------------- 配牌


def test_deal():
    g = make([J1, J2, J3, "1199m1199p1199s1z"], draws="7z", dora="1m")
    assert g.current == 0 and g.phase == Phase.TURN
    assert g.observation(0)["hand_sizes"] == [14, 13, 13, 13]
    assert g.wall_remaining == 69  # 136 - 52 - 14 - 1
    assert g.dora_indicators() == [parse_tile("1m")]
    assert g.scores == [25000] * 4 and g.dealer == 0


def test_red_and_normal_five_are_separate_discards():
    g = position(["405m147p258s1357z" + "9m", J2, J3, J1], drawn="9m")
    ids = {a.arg for a in g.legal_actions() if a.type == A.ActionType.DISCARD}
    assert parse_tile("0m") in ids and parse_tile("5m") in ids


# ---------------------------------------------------------------- 立直


def riichi_position(**kw):
    return position([TENPAI + "1z", J1, J2, J3], drawn="1z", **kw)


def test_riichi_requirements():
    assert A.RIICHI in legal(riichi_position())
    assert A.RIICHI not in legal(riichi_position(scores=[900, 25000, 25000, 25000]))
    g = riichi_position()
    g.draw_pos = LIVE_END - 3
    g._legal_cache = None
    assert A.RIICHI not in legal(g)  # 可摸的牌不到 4 张
    g.draw_pos = LIVE_END - 4
    g._legal_cache = None
    assert A.RIICHI in legal(g)
    not_tenpai = position(["123m456p789s29s55p1z", J1, J2, J3], drawn="1z")
    assert A.RIICHI not in legal(not_tenpai)
    opened = position(["456p789s23s55p1z", J1, J2, J3], drawn="1z", melds=[[pon("111m")], [], [], []])
    assert A.RIICHI not in legal(opened)


def test_riichi_flow_and_stick():
    g = riichi_position(draws="9m1p6z9p")
    act(g, 0, A.RIICHI)
    assert g.phase == Phase.RIICHI
    assert legal(g) == {A.discard(parse_tile("1z"))}  # 只能打出后仍听牌的
    act(g, 0, "1z")
    assert g.riichi[0] == 1 and g.sticks == 1 and g.scores[0] == 24000 and g.ippatsu[0]
    for s in (1, 2, 3):
        tsumogiri(g, s)
    assert legal(g) == {A.discard(parse_tile("9p"))}  # 立直后只能摸切


def test_riichi_ippatsu_tsumo_and_ura():
    g = riichi_position(draws="9m1p6z1s", dora="4z", ura="1m")
    act(g, 0, A.RIICHI)
    act(g, 0, "1z")
    for s in (1, 2, 3):
        tsumogiri(g, s)
    act(g, 0, A.TSUMO)
    (w,) = last_wins(g)
    assert yaku_names(w) == {"立直", "一发", "门前清自摸和", "平和", "里宝牌"}
    assert (w["han"], w["fu"]) == (5, 20)  # 庄家 5 番 20 符 = 满贯,每家 4000
    assert g.scores == [24000 + 12000 + 1000, 21000, 21000, 21000]
    assert g.hand_results[-1]["ura_indicators"] == [parse_tile("1m")]


def test_ippatsu_broken_by_call():
    g = position([TENPAI + "1z", J1, "99m258m369p147s46z", J3], drawn="1z", draws="9m6z1s")
    act(g, 0, A.RIICHI)
    act(g, 0, "1z")
    tsumogiri(g, 1)  # 打 9m
    act(g, 2, A.pon())
    assert not any(g.ippatsu)
    act(g, 2, "4z")
    tsumogiri(g, 3)
    act(g, 0, A.TSUMO)
    assert "一发" not in yaku_names(last_wins(g)[0])


def test_ron_on_riichi_declaration_tile_cancels_riichi():
    g = position([TENPAI + "1z", "234m456p678s11z55z", J2, J3], drawn="1z")
    act(g, 0, A.RIICHI)
    act(g, 0, "1z")
    act(g, 1, A.RON)
    (w,) = last_wins(g)
    assert w["gain"] == 1300  # 场风东 1 番 40 符
    assert g.scores[0] == 23700 and g.sticks == 0 and g.riichi[0] == 0


def test_double_riichi():
    g = position([TENPAI + "1z", J1, J2, J3], drawn="1z", mid=False, draws="9m1p6z1s")
    act(g, 0, A.RIICHI)
    act(g, 0, "1z")
    assert g.riichi[0] == 2
    for s in (1, 2, 3):
        tsumogiri(g, s)
    act(g, 0, A.TSUMO)
    assert "双立直" in yaku_names(last_wins(g)[0])


def test_no_double_riichi_after_a_call():
    g = position([TENPAI + "1z", J1, J2, J3], drawn="1z", mid=False)
    g.no_calls = False
    act(g, 0, A.RIICHI)
    act(g, 0, "1z")
    assert g.riichi[0] == 1


def set_hand(g, seat, text, drawn):
    from riichi.tiles import parse_tiles, tiles_to_counts

    g.hands[seat] = tiles_to_counts(parse_tiles(text))
    g.drawn = parse_tile(drawn)
    g._legal_cache = None


def test_riichi_ankan_only_if_waits_unchanged():
    g = position([J1, J2, J3, J1])
    g.riichi[0] = 1
    set_hand(g, 0, "123m456p23s55p1111z", "1z")  # 听 1s4s,杠了还是听 1s4s
    assert A.ankan(parse_tile("1z")) in legal(g)
    set_hand(g, 0, "33334m456p789s123s", "3m")  # 原来听 2m4m5m,杠了只听 4m
    assert A.ankan(parse_tile("3m")) not in legal(g)
    set_hand(g, 0, "123m456p23s55p1111z", "5p")  # 不是刚摸到的: 不能杠
    assert not any(a.type == A.ActionType.ANKAN for a in legal(g))


# ---------------------------------------------------------------- 吃


CHI_HOLDER = "12m45m36m69p147s24z"  # 13 张


def chi_position(seat1=CHI_HOLDER, seat2="129m369p258s1357z"):
    return position(["1347m258p369s1357z", seat1, seat2, J3], drawn="3m")


def test_chi_only_from_left_and_three_shapes():
    g = chi_position()
    act(g, 0, "3m")
    assert g.current == 1
    assert legal(g) == {A.chi(0), A.chi(1), A.chi(2), A.PASS}
    act(g, 1, A.PASS)
    assert g.current == 1 and g.phase == Phase.TURN  # 座位 2 有 12m 但不是下家,不问;下家摸牌


@pytest.mark.parametrize(
    "shape,forbidden",
    [(0, {"3m", "6m"}), (1, {"3m"}), (2, {"3m"})],
)
def test_kuikae(shape, forbidden):
    """吃完不能打現物;两面搭子吃了也不能打另一头(筋)。"""
    g = chi_position()
    act(g, 0, "3m")
    act(g, 1, A.chi(shape))
    assert g.melds[1][0].type == MeldType.CHI and g.drawn is None
    discards = {a.arg for a in legal(g)}
    for t in ("3m", "6m"):
        assert (parse_tile(t) in discards) == (t not in forbidden)
    assert A.RIICHI not in legal(g) and A.TSUMO not in legal(g)


def test_chi_illegal_when_only_forbidden_tiles_left():
    seat1_melds = [pon("999s"), pon("333z"), pon("444z")]
    g = position(["1347m258p369s1357z", "3456m", J2, J3], drawn="3m", melds=[[], seat1_melds, [], []])
    g.hands[1] = [0] * 34
    for t in ("3m", "4m", "5m", "6m"):
        g.hands[1][parse_tile(t)] += 1
    act(g, 0, "3m")
    # 用 45 吃了只剩 3m 6m,都不能打 → 不合法;能荣和(33 + 456)但没役 → 不问
    assert g.phase == Phase.TURN and g.current == 1


def test_chi_with_red_five_choice():
    g = chi_position(seat1="12m405m69p147s246z")
    act(g, 0, "3m")
    assert legal(g) == {A.chi(0, False), A.chi(0, True), A.chi(1), A.chi(2), A.PASS}
    act(g, 1, A.chi(0, True))
    assert parse_tile("0m") in g.melds[1][0].tiles and g.reds[1][0] == 0


def test_chi_only_red_available():
    g = chi_position(seat1="12m40m69p147s2467z")
    act(g, 0, "3m")
    assert A.chi(0, True) in legal(g) and A.chi(0, False) not in legal(g)


# ---------------------------------------------------------------- 碰、杠、优先级


def test_pon_beats_chi_and_ron_beats_pon():
    hands = ["5p147m258s1357z9s" + "9m", "46p147m258s1357z9m", "55p258m369s2467z1s", J3]
    g = position(hands, drawn="9m")
    g.hands[0][parse_tile("9m")] -= 1
    act(g, 0, "5p")
    act(g, 1, A.chi(1))
    act(g, 2, A.pon())
    assert g.current == 2 and g.melds[2][0].type == MeldType.PON and not g.melds[1]

    hands[3] = "234m678s34p567s22m"  # 听 2p5p,断幺
    g = position(hands, drawn="9m")
    act(g, 0, "5p")
    act(g, 1, A.chi(1))
    act(g, 2, A.pon())
    act(g, 3, A.RON)
    assert last_wins(g)[0]["seat"] == 3 and not g.melds[2]


def test_pon_with_red_choice_and_daiminkan():
    g = position(["5p147m258s1357z99s", J1, "055p258m369s246z", J3], drawn="9s")
    act(g, 0, "5p")
    assert legal(g) == {A.pon(False), A.pon(True), A.DAIMINKAN, A.PASS}


def test_daiminkan_rinshan_and_late_dora():
    g = position(["5p147m258s1357z99s", J1, "555p258m369s246z", J3], drawn="9s")
    remaining = g.wall_remaining
    act(g, 0, "5p")
    act(g, 2, A.DAIMINKAN)
    assert g.melds[2][0].type == MeldType.DAIMINKAN and len(g.melds[2][0].tiles) == 4
    assert g.current == 2 and g.after_kan and g.drawn == g.wall[135]
    assert g.dora_revealed == 1  # 明杠: 出牌之后才翻
    assert g.wall_remaining == remaining - 1
    tsumogiri(g, 2)
    assert g.dora_revealed == 2


def test_ankan_reveals_dora_immediately():
    g = position(["1111z147m258p36s" + "9s", J1, J2, J3], drawn="9s")
    act(g, 0, A.ankan(parse_tile("1z")))
    assert g.dora_revealed == 2 and g.melds[0][0].type == MeldType.ANKAN
    assert g.kan_total == 1 and g.drawn == g.wall[135]


def test_kakan():
    g = position(["5p147m258s13z" + "9s", J1, J2, J3], drawn="5p", melds=[[pon("555p", 2)], [], [], []])
    g.hands[0][parse_tile("9s")] -= 1
    g.hands[0][parse_tile("5p")] = 1
    g._legal_cache = None
    assert A.kakan(parse_tile("5p")) in legal(g)
    act(g, 0, A.kakan(parse_tile("5p")))
    assert g.melds[0][0].type == MeldType.KAKAN and len(g.melds[0][0].tiles) == 4
    assert g.dora_revealed == 1 and g.after_kan
    tsumogiri(g, 0)
    assert g.dora_revealed == 2


def test_chankan():
    melds = [[pon("555p", 2)], [], [], []]
    hand0 = "5p147m258s13z"  # 加杠前 10 张 + 刚摸的 5p
    g = position([hand0 + "9s", "234m678s34p567s22m", J2, J3], drawn="5p", melds=melds)
    g.hands[0][parse_tile("9s")] -= 1
    g._legal_cache = None
    act(g, 0, A.kakan(parse_tile("5p")))
    assert g.phase == Phase.ROB_KAN and legal(g) == {A.RON, A.PASS}
    act(g, 1, A.RON)
    (w,) = last_wins(g)
    assert "抢杠" in yaku_names(w) and w["from_seat"] == 0
    assert g.melds[0][0].type == MeldType.PON  # 杠不成立


def test_pass_on_chankan_completes_kan_and_sets_furiten():
    melds = [[pon("555p", 2)], [], [], []]
    g = position(["5p147m258s13z", "234m678s34p567s22m", J2, J3], drawn="5p", melds=melds)
    act(g, 0, A.kakan(parse_tile("5p")))
    act(g, 1, A.PASS)
    assert g.melds[0][0].type == MeldType.KAKAN and g.current == 0
    assert g.temp_furiten[1]


def test_ankan_robbed_only_by_kokushi():
    # 座位 1 国士听东,座位 2 单骑东: 只有国士能抢暗杠
    g = position(["1111z147m258p36s" + "9s", "19m19p19s2345677z", "123m456p789s1z55p", J3], drawn="9s")
    act(g, 0, A.ankan(parse_tile("1z")))
    assert g.phase == Phase.ROB_KAN and g.current == 1  # 只有国士能抢暗杠
    act(g, 1, A.RON)
    assert yaku_names(last_wins(g)[0]) == {"国士无双"}


def test_rinshan_kaihou():
    g = position(["1111z123m456p78s55p", J1, J2, J3], drawn="1z")
    g.wall[135] = parse_tile("9s")
    act(g, 0, A.ankan(parse_tile("1z")))
    act(g, 0, A.TSUMO)
    assert "岭上开花" in yaku_names(last_wins(g)[0])


def test_kan_limits():
    g = position(["1111z147m258p36s" + "9s", J1, J2, J3], drawn="9s")
    g.draw_pos = LIVE_END  # 一张都不剩: 不能杠
    g._legal_cache = None
    assert not any(a.type == A.ActionType.ANKAN for a in legal(g))
    g = position(["1111z147m258p36s" + "9s", J1, J2, J3], drawn="9s")
    g.kan_total = 4
    g._legal_cache = None
    assert not any(a.type == A.ActionType.ANKAN for a in legal(g))


# ---------------------------------------------------------------- 海底、河底


def test_haitei_tsumo():
    g = position([J1 + "9m", TENPAI, J2, J3], drawn="9m")
    g.draw_pos = LIVE_END - 1
    g.wall[LIVE_END - 1] = parse_tile("1s")
    tsumogiri(g, 0)
    assert g.wall_remaining == 0
    act(g, 1, A.TSUMO)
    assert "海底摸月" in yaku_names(last_wins(g)[0])


def test_houtei_only_ron_no_calls():
    hands = [J1 + "4s", TENPAI, "44s" + "258m369p17s246z", J3]
    g = position(hands, drawn="4s")
    g.draw_pos = LIVE_END
    act(g, 0, "4s")
    assert legal(g) == {A.RON, A.PASS}  # 座位 2 有一对 4s 也不能碰
    act(g, 1, A.RON)
    assert "河底捞鱼" in yaku_names(last_wins(g)[0])


# ---------------------------------------------------------------- 振听、没役


def test_discard_furiten_blocks_ron_not_tsumo():
    seat1 = "234m456p678s34s55p"
    g = position([J1 + "9m", seat1, J2, J3], drawn="9m", draws="2s5s9p8m2s")
    tsumogiri(g, 0)
    assert A.TSUMO in legal(g)
    tsumogiri(g, 1)  # 自摸不要,打出 2s → 舍张振听
    assert g.observation(1)["furiten"]
    tsumogiri(g, 2)  # 打 5s: 座位 1 听这张但振听,不能荣和
    assert g.current == 3 and g.phase == Phase.TURN
    tsumogiri(g, 3)
    tsumogiri(g, 0)
    assert A.TSUMO in legal(g)  # 振听可以自摸


def test_temporary_furiten():
    seat1 = "234m456p678s34s55p"
    g = position([J1 + "9m", seat1, J2, J3], drawn="9m", draws="9p2s5s1p8m5s")
    tsumogiri(g, 0)
    tsumogiri(g, 1)
    tsumogiri(g, 2)  # 2s
    assert g.current == 1 and A.RON in legal(g)
    act(g, 1, A.PASS)
    tsumogiri(g, 3)  # 5s: 同巡振听,不问
    assert g.current == 0 and g.phase == Phase.TURN
    tsumogiri(g, 0)
    tsumogiri(g, 1)  # 自己打过一张,同巡振听解除
    tsumogiri(g, 2)  # 5s
    assert g.current == 1 and A.RON in legal(g)


def test_riichi_furiten_is_permanent():
    seat1 = "234m456p678s34s55p"
    g = position([J1 + "9m", seat1, J2, J3], drawn="9m", draws="9p2s5s1p8m5s")
    tsumogiri(g, 0)
    # 座位 1 摸 9p 后立直打 9p
    act(g, 1, A.RIICHI)
    act(g, 1, "9p")
    tsumogiri(g, 2)  # 2s
    act(g, 1, A.PASS)
    tsumogiri(g, 3)
    tsumogiri(g, 0)
    tsumogiri(g, 1)  # 8m
    tsumogiri(g, 2)  # 5s: 立直振听,一直不能荣和
    assert g.current == 3 and g.phase == Phase.TURN


def test_no_yaku_no_ron_but_furiten():
    """副露后没役: 听的牌打出来不能荣和(只能吃),漏过之后同巡振听。"""
    melds = [[], [chi("789s")], [], []]
    g = position([J1 + "3m", "12m456p345s55p", J2, J3], drawn="3m", melds=melds)
    act(g, 0, "3m")
    assert legal(g) == {A.chi(2), A.PASS}
    act(g, 1, A.PASS)
    assert g.temp_furiten[1]


def test_no_yaku_no_tsumo():
    melds = [[], [chi("789s")], [], []]
    g = position([J1, "12m456p345s55p3m", J2, J3], turn=1, drawn="3m", melds=melds)
    assert A.TSUMO not in legal(g)


# ---------------------------------------------------------------- 双响、三响


def test_double_ron_head_bump_for_sticks_and_honba():
    hands = [J1 + "5p", "234m678s34p567s22m", "345m678m456s46p88s", J3]
    g = position(hands, drawn="5p")
    g.honba, g.sticks = 1, 2
    act(g, 0, "5p")
    act(g, 1, A.RON)
    act(g, 2, A.RON)
    w1, w2 = last_wins(g)
    assert (w1["seat"], w2["seat"]) == (1, 2)
    assert w1["gain"] == 2000 + 300 + 2000  # 平和断幺 2 番 30 符 + 本场 + 供托
    assert w2["gain"] == 1300  # 断幺 1 番 40 符,不拿本场和供托
    assert g.scores[0] == 25000 - 2300 - 1300


def test_triple_ron_is_abortive_draw():
    hands = [J1 + "5p", "234m678s34p567s22m", "345m678m456s46p88s", "234s678m34p678p55s"]
    g = position(hands, drawn="5p")
    act(g, 0, "5p")
    for s in (1, 2, 3):
        act(g, s, A.RON)
    r = g.hand_results[-1]
    assert r["type"] == "ryukyoku" and r["reason"] == "sanchahou" and r["deltas"] == [0, 0, 0, 0]


def test_triple_ron_allowed_when_abortive_draws_off():
    hands = [J1 + "5p", "234m678s34p567s22m", "345m678m456s46p88s", "234s678m34p678p55s"]
    g = position(hands, drawn="5p", config=RuleConfig(length="one", abortive_draws=False))
    act(g, 0, "5p")
    for s in (1, 2, 3):
        act(g, s, A.RON)
    assert len(last_wins(g)) == 3


# ---------------------------------------------------------------- 荒牌流局、流局满贯


@pytest.mark.parametrize(
    "tenpai_seats,deltas",
    [
        ((0,), [3000, -1000, -1000, -1000]),
        ((0, 1), [1500, 1500, -1500, -1500]),
        ((0, 1, 2), [1000, 1000, 1000, -3000]),
        ((), [0, 0, 0, 0]),
        ((0, 1, 2, 3), [0, 0, 0, 0]),
    ],
)
def test_exhaustive_draw_payments(tenpai_seats, deltas):
    junk = [J1, J2, J3, J1]
    hands = [TENPAI if s in tenpai_seats else junk[s] for s in range(4)]
    hands[0] += "8m"
    g = position(hands, drawn="8m")
    g.draw_pos = LIVE_END
    act(g, 0, "8m")
    r = g.hand_results[-1]
    assert r["reason"] == "exhaustive" and r["deltas"] == deltas
    assert r["tenpai"] == [s in tenpai_seats for s in range(4)]


def test_tenpai_on_own_fourth_tile_does_not_count():
    """单骑 5p,但另外 3 张 5p 在自己的碰里: 不算听牌。"""
    g = position([J1, "123m456s789s5p", J2, J3], melds=[[], [pon("555p")], [], []])
    assert not g.is_tenpai(1)
    g = position([J1, "123m456s789s6p", J2, J3], melds=[[], [pon("555p")], [], []])
    assert g.is_tenpai(1)


@pytest.mark.parametrize("dealer_tenpai,expect_dealer", [(True, 0), (False, 1)])
def test_exhaustive_draw_renchan(dealer_tenpai, expect_dealer):
    hands = [(TENPAI if dealer_tenpai else J2) + "8m", J1, J2, J3]
    g = position(hands, drawn="8m", config=HANCHAN)
    g.draw_pos = LIVE_END
    act(g, 0, "8m")
    assert g.dealer == expect_dealer and g.honba == 1 and g.kyoku == expect_dealer


def test_nagashi_mangan():
    hands = [J2 + "8m", TENPAI, J3, J1]
    g = position(hands, drawn="8m")
    g.discards[2] = [parse_tile(t) for t in ("1m", "9p", "1z", "7z")]
    g.discard_flags[2] = [[True, False, False] for _ in range(4)]
    g.discards[3] = [parse_tile("5m")]
    g.discard_flags[3] = [[True, False, False]]
    g.draw_pos = LIVE_END
    act(g, 0, "8m")
    r = g.hand_results[-1]
    assert r["reason"] == "nagashi_mangan" and r["nagashi"] == [2]
    assert r["deltas"] == [-4000, -2000, 8000, -2000]  # 没有罚符


def test_nagashi_broken_if_discard_was_called():
    hands = [J2 + "8m", TENPAI, J3, J1]
    g = position(hands, drawn="8m")
    g.discards[2] = [parse_tile(t) for t in ("1m", "9p")]
    g.nagashi_ok[2] = False
    g.draw_pos = LIVE_END
    act(g, 0, "8m")
    assert g.hand_results[-1]["reason"] == "exhaustive"


def test_nagashi_switch():
    hands = [J2 + "8m", TENPAI, J3, J1]
    g = position(hands, drawn="8m", config=RuleConfig(length="one", nagashi_mangan=False))
    g.discards[2] = [parse_tile("1m")]
    g.draw_pos = LIVE_END
    act(g, 0, "8m")
    assert g.hand_results[-1]["reason"] == "exhaustive"


# ---------------------------------------------------------------- 途中流局


KYUUSHU_HAND = "19m19p19s1234z55m" + "8p"  # 9 种幺九 + 摸的 8p


def test_kyuushu():
    g = position([KYUUSHU_HAND, J1, J2, J3], drawn="8p", mid=False, config=HANCHAN)
    assert A.KYUUSHU in legal(g)
    act(g, 0, A.KYUUSHU)
    assert g.hand_results[-1]["reason"] == "kyuushu"
    assert g.dealer == 0 and g.honba == 1  # 途中流局连庄


def test_kyuushu_conditions():
    assert A.KYUUSHU not in legal(position([KYUUSHU_HAND, J1, J2, J3], drawn="8p", mid=True))
    g = position([KYUUSHU_HAND, J1, J2, J3], drawn="8p", mid=False)
    g.no_calls = False
    g._legal_cache = None
    assert A.KYUUSHU not in legal(g)
    eight = position(["19m19p19s12z555m888p", J1, J2, J3], drawn="8p", mid=False)
    assert A.KYUUSHU not in legal(eight)
    off = position([KYUUSHU_HAND, J1, J2, J3], drawn="8p", mid=False, config=RuleConfig(length="one", abortive_draws=False))
    assert A.KYUUSHU not in legal(off)


def test_suufon_renda():
    hands = ["1z258m369s147p246z" + "8p", "1z147m258p369s357z", "1z369m147p258s357z", "1z258m369p147s246z"]
    g = position(hands, drawn="8p", mid=False, draws="9m9p9s")
    act(g, 0, "1z")
    for s in (1, 2, 3):
        act(g, s, "1z")
    assert g.hand_results[-1]["reason"] == "suufon_renda"


def test_suukaikan_two_players():
    g = position(["1111z147m258p36s" + "9s", J1, J2, J3], drawn="9s")
    g.kan_total, g.kans_by = 3, [2, 1, 0, 0]
    g._legal_cache = None
    act(g, 0, A.ankan(parse_tile("1z")))
    tsumogiri(g, 0)
    assert g.hand_results[-1]["reason"] == "suukaikan"


def test_four_kans_by_one_player_no_abort_but_no_more_kans():
    g = position(["1111z147m258p36s" + "9s", J1, J2, J3], drawn="9s")
    g.kan_total, g.kans_by = 3, [3, 0, 0, 0]
    g._legal_cache = None
    act(g, 0, A.ankan(parse_tile("1z")))
    tsumogiri(g, 0)
    assert not g.hand_results and g.current == 1
    assert g.kan_total == 4


def test_suucha_riichi():
    g = position([J1, J2, J3, TENPAI + "1z"], turn=3, drawn="1z")
    g.riichi = [1, 1, 1, 0]
    act(g, 3, A.RIICHI)
    act(g, 3, "1z")
    r = g.hand_results[-1]
    assert r["reason"] == "suucha_riichi"
    # 立直棒照交;只打一局,结束时桌上的供托归第一名(同分时座位 0 在前)
    assert g.scores == [26000, 25000, 25000, 24000]


# ---------------------------------------------------------------- 包牌、本场


def pao_position(draws=""):
    melds = [[pon("555z", 2), pon("666z", 3)], [], [], []]
    return position(["123m45p77z", J1 + "7z", J2, J3], turn=1, drawn="7z", melds=melds, draws=draws)


def test_pao_daisangen_tsumo():
    g = pao_position(draws="9m9p9s4p")
    act(g, 1, "7z")
    act(g, 0, A.pon())
    assert g.pao[0] == {"大三元": 1}
    act(g, 0, "5p")  # 单骑 4p
    tsumogiri(g, 1)
    tsumogiri(g, 2)
    tsumogiri(g, 3)
    act(g, 0, A.TSUMO)
    (w,) = last_wins(g)
    assert w["payments"] == [(1, 0, 48000)]  # 庄家役满,包牌者一人付


def test_pao_daisangen_ron_split():
    g = pao_position(draws="9m4p")
    act(g, 1, "7z")
    act(g, 0, A.pon())
    act(g, 0, "5p")
    tsumogiri(g, 1)
    tsumogiri(g, 2)  # 座位 2 打 4p
    act(g, 0, A.RON)
    (w,) = last_wins(g)
    assert sorted(w["payments"]) == [(1, 0, 24000), (2, 0, 24000)]


def test_honba_payments():
    g = position([J1 + "9m", TENPAI, J2, J3], drawn="9m", draws="1s")
    g.honba = 2
    tsumogiri(g, 0)
    act(g, 1, A.TSUMO)
    (w,) = last_wins(g)
    # 闲家 门前清自摸和 + 平和 2 番 20 符: 400 / 700,每家再加 200
    assert sorted(w["payments"]) == sorted([(0, 1, 900), (2, 1, 600), (3, 1, 600)])

    g = position([TENPAI, J1, J2, J3[:-2] + "1s" + "4z"], turn=3, drawn="4z")
    g.honba = 2
    act(g, 3, "1s")
    act(g, 0, A.RON)
    (w,) = last_wins(g)
    assert w["gain"] == 1500 + 600  # 庄家平和 1 番 30 符 1500


# ---------------------------------------------------------------- 天和、地和


def test_tenhou_and_chiihou():
    g = position(["123m456p789s11222z", J1, J2, J3], drawn="2z", mid=False)
    act(g, 0, A.TSUMO)
    assert "天和" in yaku_names(last_wins(g)[0])
    g = position([J1, "123m456p789s11222z", J2, J3], turn=1, drawn="2z", mid=False)
    act(g, 1, A.TSUMO)
    assert "地和" in yaku_names(last_wins(g)[0])
    g = position([J1, "123m456p789s11222z", J2, J3], turn=1, drawn="2z", mid=False)
    g.no_calls = False
    g._legal_cache = None
    act(g, 1, A.TSUMO)
    assert "地和" not in yaku_names(last_wins(g)[0])


# ---------------------------------------------------------------- 视图、非法动作


def test_observation_hides_private_info():
    g = make([J1, J2, J3, "1199m1199p1199s1z"], draws="7z")
    obs = g.observation(1)
    assert obs["hand"] == g.hand_tiles(1) and obs["drawn"] is None and obs["legal_actions"] == []
    assert "hands" not in obs and "wall" not in obs
    assert obs["dora_indicators"] == g.dora_indicators()
    assert all(ev.get("tile") is None for ev in g.events_for(1) if ev["type"] == "draw" and ev["seat"] != 1)
    assert g.observation(0)["drawn"] == parse_tile("7z")


def test_illegal_action_leaves_state_unchanged():
    g = make([J1, J2, J3, "1199m1199p1199s1z"], draws="7z")
    before = (list(g.history), g.current, g.observation(0))
    with pytest.raises(IllegalAction):
        g.step(A.RON)
    with pytest.raises(IllegalAction):
        g.step(999)
    assert (list(g.history), g.current, g.observation(0)) == before

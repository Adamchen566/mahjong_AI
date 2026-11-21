from ai import RuleAgent, make_agent
from ai.evaluate import evaluate
from chuanma import Game, RuleConfig
from chuanma.actions import HU, PASS, PONG, ActionType, discard
from chuanma.tiles import parse_tile, parse_tiles

from helpers import JUNK, SOU, make_game
from test_invariants import check_final_state, play_checked

T = parse_tile


def decide(game):
    return RuleAgent().act(game.observation(game.current), game.legal_actions())


def test_discards_the_useless_tile():
    # 123m456m789m 23p 99p + 5s... 这里缺条,手里没有条;多出来的孤张是 6p
    g = make_game(["123m456m789m23p99p6p", JUNK, JUNK, JUNK], wall="9m9m")
    assert decide(g) == discard(T("6p"))


def test_prefers_the_wider_wait():
    # 打 1p 留 34p 两面听(2p/5p 共 8 张);打 4p 留 13p 嵌张(2p 4 张)
    g = make_game(["123m456m789m134p99p", JUNK, JUNK, JUNK], wall="9m9m")
    assert decide(g) == discard(T("1p"))


def test_tenpai_counts_only_tiles_still_available():
    # 同上,但 2p 和 5p 都已经被打光: 两面听变成死听,嵌张也死,退而看别的
    g = make_game(["123m456m789m134p99p", JUNK, JUNK, JUNK], wall="9m9m")
    g.discards[1] = parse_tiles("2222p5555p")
    choice = decide(g)
    assert choice.type == ActionType.DISCARD  # 不崩溃,给出合法动作
    assert choice in g.legal_actions()


def test_always_takes_the_win():
    g = make_game(["123m456m789m123p55p", JUNK, JUNK, JUNK], wall="9m")
    assert decide(g) == HU


def test_pongs_when_it_gets_closer():
    # 两个面子 + 22p + 99p + 468p: 一向听。碰 2p 后变成听牌
    hand = "123m456m22p99p468p"
    g = make_game([JUNK + "2p", hand, JUNK, JUNK], wall="9m9m")
    g.step(discard(T("2p")))
    assert g.current == 1 and g.legal_actions() == [PONG, PASS]
    assert decide(g) == PONG


def test_passes_on_a_pong_that_breaks_a_good_shape():
    # 223344m 是两个顺子;碰 3m 会把它拆坏
    hand = "223344m567m23p99p"
    g = make_game([JUNK + "3m", hand, JUNK, JUNK], wall="9m9m")
    g.step(discard(T("3m")))
    assert g.current == 1
    assert decide(g) == PASS


def test_chooses_the_void_suit_that_hurts_least():
    g = Game(config=RuleConfig(exchange_three=False), seed=5)
    obs = g.observation(g.current)
    obs["hand"] = parse_tiles("123m456m789m12p3s9s")  # 条最少也最散
    choice = RuleAgent().act(obs, g.legal_actions())
    assert choice.tile == SOU


def test_exchange_gives_away_the_short_suit_consistently():
    g = Game(seed=5)
    seat = g.current
    start = parse_tiles("123m456m789m12p") + parse_tiles("159s")
    agent = RuleAgent()
    given = []
    for _ in range(3):
        obs = g.observation(seat)
        hand = list(start)
        for t in given:
            hand.remove(t)
        obs["hand"] = hand
        obs["exchange"] = {"given": list(given), "received": [], "direction": None}
        legal = [a for a in g.legal_actions()]  # 类型都是 EXCHANGE,这里只用来走流程
        choice = agent.act(obs, legal)
        assert choice.type == ActionType.EXCHANGE
        given.append(choice.tile)
    assert sorted(given) == parse_tiles("159s")


def test_four_rule_agents_play_clean_games():
    agents = [make_agent("rule") for _ in range(4)]
    reasons = set()
    for seed in range(60):
        game = play_checked(agents, seed, RuleConfig(), check_every_step=seed % 10 == 0)
        check_final_state(game)
        reasons.add(game.end_reason)
    assert "three_won" in reasons


def test_rule_agent_beats_simple_agent():
    result = evaluate("rule", "simple", num_deals=60, seed=0)
    assert result.games == 240
    assert result.mean > 0

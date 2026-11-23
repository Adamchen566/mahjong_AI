"""日麻状态编码: 训练用的 encode 和对局软件用的 encode_obs 在每个决策点完全一样;不偷看。"""
import numpy as np

from riichi import Game, RandomAgent, ShantenAgent
from riichi_ai.encoding import (
    CHANNEL_OFFSET,
    NUM_CHANNELS,
    OBS_SCALE,
    ORACLE_SHAPE,
    danger_labels,
    encode,
    encode_obs,
    encode_oracle,
)


def play(agents, seed, check):
    game = Game(seed=seed)
    while not game.is_over:
        s = game.current
        check(game)
        game.step(agents[s].act(game.observation(s), game.legal_actions()))


def test_encode_matches_encode_obs_for_every_seat():
    agents = [ShantenAgent(0), RandomAgent(1), ShantenAgent(2), RandomAgent(3)]
    count = [0]

    def check(game):
        for seat in range(4):
            a = encode(game, seat)
            b = encode_obs(game.observation(seat))
            assert a.shape == (NUM_CHANNELS, 34) and a.dtype == np.uint8
            assert np.array_equal(a, b), seat
        count[0] += 1

    for seed in range(3):
        play(agents, seed, check)
    assert count[0] > 500


def test_values_within_scale():
    agents = [ShantenAgent(s) for s in range(4)]

    def check(game):
        x = encode(game, game.current).astype(np.float32) * OBS_SCALE[:, None]
        assert x.max() <= 1.0 + 1e-6

    play(agents, 5, check)


def test_encoding_does_not_depend_on_hidden_tiles():
    """把对手的手牌换掉,自己的编码不变;看全场的输入会变。"""
    game = Game(seed=9)
    before = encode(game, 0)
    oracle_before = encode_oracle(game, 0)
    game.hands[1], game.hands[2] = game.hands[2], game.hands[1]
    assert np.array_equal(before, encode(game, 0))
    assert not np.array_equal(oracle_before, encode_oracle(game, 0))
    assert oracle_before.shape == ORACLE_SHAPE


def test_hand_channels():
    game = Game(seed=4)
    x = encode(game, 0)
    hand = x[CHANNEL_OFFSET["hand"] : CHANNEL_OFFSET["hand"] + 4]
    assert hand[0].sum() == len({t if t < 34 else [4, 13, 22][t - 34] for t in game.hand_tiles(0)})
    assert hand.sum() == 14  # 庄家 14 张


def test_danger_labels_match_ron_options():
    """标签说"打这张会被荣和"时,打出去确实有人能荣和;反之没人能。"""
    agents = [ShantenAgent(s) for s in range(4)]
    checked = [0]

    def check(game):
        from riichi.game import Phase

        if game.phase != Phase.TURN or game.drawn is None:
            return
        seat = game.current
        labels = danger_labels(game, seat)
        for a in game.legal_actions():
            if a.type.name != "DISCARD":
                continue
            k = a.arg if a.arg < 34 else [4, 13, 22][a.arg - 34]
            import copy

            g = copy.deepcopy(game)
            g.record_events = False
            g.step(a)
            before = len(game.hand_results)
            can_ron = any(any(x.type.name == "RON" for x in g.resp_options.get(p, [])) for p in range(4))
            if g.phase.name == "RESPONSE" or (len(g.hand_results) == before and g.phase.name == "TURN"):
                assert bool(labels[k]) == can_ron, (k, labels[k], can_ron)
            checked[0] += 1

    game = Game(seed=21)
    n = 0
    while not game.is_over and n < 400:
        check(game)
        s = game.current
        game.step(agents[s].act(game.observation(s), game.legal_actions()))
        n += 1
    assert checked[0] > 50

"""状态编码: 和 observation() 一致、不泄露别人的牌、各通道的含义正确。"""
import random

import numpy as np
import pytest

from ai.encoding import (
    CHANNEL_GROUPS,
    CHANNEL_OFFSET,
    NUM_CHANNELS,
    OBS_SCALE,
    OBS_SHAPE,
    ORACLE_SHAPE,
    encode,
    encode_obs,
    encode_oracle,
    legal_mask,
)
from chuanma import Game, MeldType, NUM_ACTIONS, Phase, RandomAgent, RuleConfig, SimpleAgent
from chuanma.tiles import full_wall

CONFIGS = [RuleConfig(), RuleConfig(exchange_three=False, zimo_mode="jia_fan")]


def walk(seed, agent_cls=RandomAgent, config=None):
    """打一局,每个决策点之前把 game 交出来。"""
    game = Game(config=config, seed=seed, dealer=seed % 4, record_events=False)
    agents = [agent_cls(seed * 10 + s) for s in range(4)]
    while not game.is_over:
        yield game
        seat = game.current
        game.step(agents[seat].act(game.observation(seat), game.legal_actions()))


def group(arr, name):
    start = CHANNEL_OFFSET[name]
    size = next(n for g, n, _, _ in CHANNEL_GROUPS if g == name)
    return arr[start : start + size]


def test_shape_and_channel_table():
    assert OBS_SHAPE == (NUM_CHANNELS, 27)
    assert sum(n for _, n, _, _ in CHANNEL_GROUPS) == NUM_CHANNELS
    assert OBS_SCALE.shape == (NUM_CHANNELS,)
    game = Game(seed=1)
    arr = encode(game, game.current)
    assert arr.shape == OBS_SHAPE and arr.dtype == np.uint8


@pytest.mark.parametrize("agent_cls", [RandomAgent, SimpleAgent])
@pytest.mark.parametrize("config", CONFIGS)
def test_matches_observation_at_every_decision(agent_cls, config):
    """直接读 Game 的编码和只靠 observation() 的编码必须一样 —— 也就证明前者没有偷看。"""
    states = 0
    for seed in range(25):
        for game in walk(seed, agent_cls, config):
            for seat in range(4):  # 不只是当前决策者,四个座位的视角都比
                direct = encode(game, seat)
                via_obs = encode_obs(game.observation(seat))
                assert np.array_equal(direct, via_obs), (seed, len(game.history), seat)
            states += 1
    assert states > 1000


def test_values_stay_in_range():
    for seed in range(15):
        for game in walk(seed):
            arr = encode(game, game.current)
            scaled = arr.astype(np.float32) * OBS_SCALE[:, None]
            assert scaled.max() <= 1.0
            # 标量通道整行是同一个数
            scalars = arr[CHANNEL_OFFSET["phase"] :]
            assert (scalars == scalars[:, :1]).all()


def test_other_players_tiles_do_not_change_encoding():
    """只打乱别人的牌和牌墙,座位 0 开局时的编码不变。"""
    rng = random.Random(7)
    wall = full_wall()
    rng.shuffle(wall)
    other = wall[:13] + rng.sample(wall[13:], len(wall) - 13)
    a = Game(wall=wall, dealer=1, exchange_direction=1)
    b = Game(wall=other, dealer=1, exchange_direction=1)
    assert a.hands[0] == b.hands[0] and a.hands[1] != b.hands[1]
    assert np.array_equal(encode(a, 0), encode(b, 0))
    assert not np.array_equal(encode_oracle(a, 0), encode_oracle(b, 0))


def test_unseen_counts_match_the_truth():
    """"没见过的张数"应当正好等于: 别人手里的 + 牌墙里的 + 别人的暗杠 + 换三张途中的牌。"""
    checked = 0
    for seed in range(20):
        for game in walk(seed, SimpleAgent):
            seat = game.current
            truth = [0] * 27
            for s in range(4):
                if s != seat:
                    for t in range(27):
                        truth[t] += game.hands[s][t]
                    for m in game.melds[s]:
                        if m.type == MeldType.AN_GANG:
                            truth[m.tile] += 4
            for t in game.wall[game.wall_pos :]:
                truth[t] += 1
            if not game.exchange_done:
                for out in game.exchange_out:
                    for t in out:
                        truth[t] += 1
            for w in game.wins:  # 别人自摸的那张亮过了,但还算在他手里
                if w.zimo and w.tile is not None and w.seat != seat:
                    truth[w.tile] -= 1
            unseen = group(encode(game, seat), "unseen")
            assert unseen.sum(axis=0).tolist() == truth, (seed, len(game.history))
            assert (np.diff(unseen.astype(int), axis=0) <= 0).all()  # 温度计式: 上层不会比下层多
            checked += 1
    assert checked > 500


def test_hand_and_discards_are_thermometer_counts():
    for game in walk(3, SimpleAgent):
        seat = game.current
        arr = encode(game, seat)
        assert group(arr, "hand").sum(axis=0).tolist() == game.hands[seat]
        piles = group(arr, "discard")
        for rel in range(4):
            pile = game.discards[(seat + rel) % 4]
            want = [pile.count(t) for t in range(27)]
            assert piles[rel * 4 : rel * 4 + 4].sum(axis=0).tolist() == want
            last = group(arr, "last_discard")[rel]
            assert last.sum() == (1 if pile else 0)
            if pile:
                assert last[pile[-1]] == 1


def test_seats_are_relative():
    game = Game(seed=5, dealer=2)
    while game.phase != Phase.TURN:
        game.step(game.legal_action_ids()[0])
    for seat in range(4):
        arr = encode(game, seat)
        voids = group(arr, "void")
        for rel in range(4):
            suit = game.void[(seat + rel) % 4]
            want = np.zeros(27, dtype=np.uint8)
            want[suit * 9 : suit * 9 + 9] = 1
            assert np.array_equal(voids[rel], want)
        dealer = group(arr, "dealer")[:, 0].tolist()
        assert dealer.index(1) == (2 - seat) % 4 and sum(dealer) == 1
        assert group(arr, "wall")[0, 0] == game.wall_remaining


def test_voids_hidden_until_everyone_has_chosen():
    game = Game(seed=2, config=RuleConfig(exchange_three=False))
    game.step(game.legal_action_ids()[0])  # 庄家先定缺
    assert game.phase == Phase.CHOOSE_VOID
    seat = game.current
    voids = group(encode(game, seat), "void")
    assert voids.sum() == 0  # 自己还没选,别人选了的也看不到
    voids_dealer = group(encode(game, game.dealer), "void")
    assert voids_dealer[0].sum() == 9 and voids_dealer[1:].sum() == 0


def test_legal_mask():
    for game in walk(4):
        mask = legal_mask(game)
        assert mask.shape == (NUM_ACTIONS,) and mask.dtype == np.bool_
        assert np.flatnonzero(mask).tolist() == sorted(game.legal_action_ids())


def test_oracle_holds_everything_the_seat_cannot_see():
    for game in walk(6, SimpleAgent):
        seat = game.current
        arr = encode_oracle(game, seat)
        assert arr.shape == ORACLE_SHAPE
        for rel in range(1, 4):
            hand = game.hands[(seat + rel) % 4]
            assert arr[(rel - 1) * 4 : rel * 4].sum(axis=0).tolist() == hand
        assert arr[12:].sum() == game.wall_remaining

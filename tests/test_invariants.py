"""随机对局下的不变量: 不报错、牌不多不少、分数守恒、可复现、可复盘。

对局数由环境变量 CHUANMA_FUZZ_GAMES 控制(默认 300)。阶段 1 的验收用 10000:

    PowerShell:  $env:CHUANMA_FUZZ_GAMES = 10000; python -m pytest tests/test_invariants.py
"""
import os

import pytest

from chuanma import Game, GameRecord, RandomAgent, RuleConfig, SimpleAgent, replay
from chuanma.game import Phase

from helpers import assert_tiles_conserved

FUZZ_GAMES = int(os.environ.get("CHUANMA_FUZZ_GAMES", "300"))

CONFIGS = [
    RuleConfig(),
    RuleConfig(exchange_three=False, zimo_mode="jia_fan", max_fan=3),
    RuleConfig(zimo_mode="none", men_qing_zhong_zhang=False, tui_shui=False),
]


def play_checked(agents, seed, config, check_every_step):
    game = Game(config=config, seed=seed, dealer=seed % 4)
    steps = 0
    while not game.is_over:
        seat = game.current
        legal = game.legal_actions()
        assert legal, "轮到某人时必须至少有一个合法动作"
        obs = game.observation(seat)
        assert obs["legal_actions"] == [a.id for a in legal]
        game.step(agents[seat].act(obs, legal))
        steps += 1
        assert steps < 1000, "牌局没有正常结束"
        if check_every_step:
            assert_tiles_conserved(game)
            assert sum(game.scores) == 0
    return game


def check_final_state(game):
    assert game.phase == Phase.END
    assert_tiles_conserved(game)
    assert sum(game.scores) == 0
    assert sum(t.amount for t in game.transfers if t.payee == 0) - sum(
        t.amount for t in game.transfers if t.payer == 0
    ) == game.scores[0]
    winners = sum(game.won)
    assert len(game.wins) == winners
    if game.end_reason == "three_won":
        assert winners == 3
    else:
        assert game.end_reason == "wall_exhausted"
        assert winners <= 2 and game.wall_remaining == 0
    zimo_winners = {w.seat for w in game.wins if w.zimo}
    for seat in range(4):
        size = sum(game.hands[seat])
        expected = 13 - 3 * len(game.melds[seat]) + (1 if seat in zimo_winners else 0)
        assert size == expected
        # 胡了的人手里不可能还有缺门牌
        if game.won[seat]:
            void = game.void[seat]
            assert not any(game.hands[seat][void * 9 : void * 9 + 9])
    for w in game.wins:
        assert w.capped_fan <= game.config.max_fan


@pytest.mark.parametrize("agent_cls", [RandomAgent, SimpleAgent])
@pytest.mark.parametrize("config_index", range(len(CONFIGS)))
def test_fuzz(agent_cls, config_index):
    config = CONFIGS[config_index]
    agents = [agent_cls(100 + s) for s in range(4)]
    end_reasons = set()
    for seed in range(FUZZ_GAMES):
        game = play_checked(agents, seed, config, check_every_step=seed % 10 == 0)
        check_final_state(game)
        end_reasons.add(game.end_reason)
    if agent_cls is SimpleAgent and FUZZ_GAMES >= 100:
        assert end_reasons == {"three_won", "wall_exhausted"}  # 两种结束方式都覆盖到


def test_same_seed_same_game():
    def run():
        agents = [SimpleAgent(s) for s in range(4)]
        return play_checked(agents, seed=42, config=RuleConfig(), check_every_step=False)

    a, b = run(), run()
    assert a.history == b.history
    assert a.scores == b.scores
    assert a.events == b.events


def test_different_seeds_differ():
    walls = {tuple(Game(seed=s).wall) for s in range(20)}
    assert len(walls) == 20


def test_replay_round_trip(tmp_path):
    for seed in range(30):
        agents = [SimpleAgent(s) for s in range(4)]
        game = play_checked(agents, seed, RuleConfig(), check_every_step=False)
        path = tmp_path / f"{seed}.json"
        GameRecord.from_game(game, meta={"agents": "simple"}).save(path)
        record = GameRecord.load(path)
        assert record.wall is None  # 有种子就不必存牌墙
        again = replay(record)
        assert again.is_over
        assert again.scores == game.scores
        assert again.history == game.history
        assert [h for h in again.hands] == [h for h in game.hands]
        assert again.events == game.events


def test_replay_partial_and_tamper_detection():
    agents = [SimpleAgent(s) for s in range(4)]
    game = play_checked(agents, 5, RuleConfig(), check_every_step=False)
    record = GameRecord.from_game(game)
    half = replay(record, upto=len(record.actions) // 2)
    assert not half.is_over
    assert half.history == record.actions[: len(record.actions) // 2]
    record.scores = [s + 1 for s in record.scores]
    with pytest.raises(ValueError):
        replay(record)


def test_replay_custom_wall():
    wall = list(Game(seed=9).wall)
    wall.reverse()
    game = Game(wall=wall, exchange_direction=2)
    agents = [SimpleAgent(s) for s in range(4)]
    while not game.is_over:
        game.step(agents[game.current].act(game.observation(game.current), game.legal_actions()))
    record = GameRecord.from_dict(GameRecord.from_game(game).to_dict())
    assert record.wall == wall
    assert replay(record).scores == game.scores

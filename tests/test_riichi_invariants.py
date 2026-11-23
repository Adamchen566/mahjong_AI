"""日麻: 随机对局下的不变量。不报错、牌不多不少、点数守恒、可复现、可复盘。

场数由环境变量 RIICHI_FUZZ_GAMES 控制(默认 30 场半庄)。大规模验收用 tools/riichi_soak.py(多进程)。
"""
import os

import pytest

from riichi import Game, GameRecord, RandomAgent, RuleConfig, ShantenAgent, SimpleAgent, replay
from riichi.invariants import check_final, check_step

FUZZ_GAMES = int(os.environ.get("RIICHI_FUZZ_GAMES", "30"))

CONFIGS = [
    RuleConfig(),
    RuleConfig(length="tonpu", aka=False, kuitan=False, abortive_draws=False, nagashi_mangan=False, pao=False),
    RuleConfig(tobi=False, kazoe=False, uma=(30, 10, -10, -30)),
]


def play_checked(agents, seed, config, every_step=True):
    game = Game(config=config, seed=seed, record_events=False)
    steps = 0
    while not game.is_over:
        seat = game.current
        legal = game.legal_actions()
        obs = game.observation(seat)
        assert obs["legal_actions"] == [a.id for a in legal]
        game.step(agents[seat].act(obs, legal))
        steps += 1
        assert steps < 20000, "一场没有正常结束"
        if every_step:
            check_step(game)
    check_final(game)
    return game


@pytest.mark.parametrize("agent_cls", [RandomAgent, SimpleAgent, ShantenAgent])
@pytest.mark.parametrize("config_index", range(len(CONFIGS)))
def test_fuzz(agent_cls, config_index):
    agents = [agent_cls(100 + s) for s in range(4)]
    games = FUZZ_GAMES if agent_cls is not ShantenAgent else max(1, FUZZ_GAMES // 3)
    for seed in range(games):
        play_checked(agents, seed, CONFIGS[config_index], every_step=seed % 3 == 0)


def test_mixed_table_covers_many_situations():
    """四种不同的策略同桌,统计出现过的事件类型,确保主要情形都被随机对局走到。"""
    from riichi.agents import ShantenAgent as S

    kinds = set()
    reasons = set()
    for seed in range(max(4, FUZZ_GAMES // 3)):
        agents = [S(seed), RandomAgent(seed), S(seed + 1), SimpleAgent(seed)]
        game = Game(seed=seed)
        while not game.is_over:
            s = game.current
            game.step(agents[s].act(game.observation(s), game.legal_actions()))
            check_step(game)
        check_final(game)
        kinds |= {ev["type"] for ev in game.events}
        reasons |= {r["reason"] for r in game.hand_results}
    assert {"draw", "discard", "riichi", "riichi_accepted", "pon", "chi", "hand_end", "game_end"} <= kinds
    assert {"ron", "tsumo", "exhaustive"} <= reasons


def test_same_seed_same_game():
    def run():
        agents = [ShantenAgent(s) for s in range(4)]
        game = Game(seed=42)
        while not game.is_over:
            s = game.current
            game.step(agents[s].act(game.observation(s), game.legal_actions()))
        return game

    a, b = run(), run()
    assert a.history == b.history and a.scores == b.scores and a.events == b.events


def test_different_seeds_differ():
    a = Game(seed=1)
    b = Game(seed=2)
    assert a.wall != b.wall


def test_record_roundtrip(tmp_path):
    agents = [ShantenAgent(s) for s in range(4)]
    game = play_checked(agents, 7, RuleConfig(), every_step=False)
    path = tmp_path / "g.json"
    GameRecord.from_game(game, meta={"note": "test"}).save(path)
    again = replay(GameRecord.load(path))
    assert again.scores == game.scores and again.history == game.history
    half = replay(GameRecord.load(path), upto=len(game.history) // 2)
    assert not half.is_over


def test_record_with_custom_walls_and_tampering(tmp_path):
    from riichi.tiles import full_wall

    walls = [full_wall()[::-1]]
    agents = [SimpleAgent(s) for s in range(4)]
    game = Game(config=RuleConfig(length="one"), walls=walls)
    while not game.is_over:
        s = game.current
        game.step(agents[s].act(game.observation(s), game.legal_actions()))
    rec = GameRecord.from_game(game)
    assert rec.walls is not None
    assert replay(rec).scores == game.scores
    rec.scores = [s + 100 for s in rec.scores[:2]] + rec.scores[2:]
    with pytest.raises(ValueError):
        replay(rec)

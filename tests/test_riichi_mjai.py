"""引擎事件 → mjai 的转换,以及 mjai 回应 → 本项目动作。不需要 Mortal;装了 Mortal 时多跑一场同桌。"""
import pytest

from riichi import actions as A
from riichi.agents import ShantenAgent
from riichi.game import NUM_SEATS, Game
from riichi.tiles import NUM_TILE_CODES
from riichi_ai.mjai import (
    MORTAL_ACTIONS,
    MjaiConverter,
    mjai_to_tile,
    mortal_index_to_actions,
    reaction_to_action,
    tile_to_mjai,
)
from riichi_ai.mortal import MORTAL_DIR


def test_tile_round_trip():
    names = [tile_to_mjai(t) for t in range(NUM_TILE_CODES)]
    assert len(set(names)) == NUM_TILE_CODES
    assert names[0] == "1m" and names[27] == "E" and names[31] == "P" and names[33] == "C" and names[34] == "5mr"
    assert all(mjai_to_tile(n) == t for t, n in enumerate(names))


def _played(seed):
    game = Game(seed=seed)
    agents = [ShantenAgent(seed * 10 + s) for s in range(NUM_SEATS)]
    while not game.is_over:
        s = game.current
        legal = game.legal_actions()
        game.step(agents[s].act(game.observation(s), legal))
    return game


def test_converted_stream_is_consistent_for_every_seat():
    """每个座位: 只看得到自己的配牌和摸牌;手牌张数按 mjai 事件推算始终合理;结构完整。"""
    # 逐步转换(加杠宣言要在当步转换),这里用一场重放来模拟
    for seed in (1, 2, 3):
        ref = _played(seed)
        game = Game(seed=seed)
        convs = [MjaiConverter(s) for s in range(NUM_SEATS)]
        streams = [[] for _ in range(NUM_SEATS)]
        cursor = 0

        def pump():
            nonlocal cursor
            for ev in game.events[cursor:]:
                for s in range(NUM_SEATS):
                    streams[s].extend(convs[s].convert(ev, game))
            cursor = len(game.events)

        pump()
        for a in ref.history:
            game.step(a)
            pump()
        for s, st in enumerate(streams):
            types = [m["type"] for m in st]
            assert types[0] == "start_game" and types[-1] == "end_game"
            assert types.count("start_kyoku") == len(ref.hand_results) == types.count("end_kyoku")
            for m in st:
                if m["type"] == "start_kyoku":
                    for p, tehai in enumerate(m["tehais"]):
                        assert len(tehai) == 13
                        assert (p == s) == ("?" not in tehai)
                if m["type"] == "tsumo":
                    assert (m["pai"] == "?") == (m["actor"] != s)
            # 推算自己的手牌张数: 摸 +1,打 −1,吃碰 −2,大明杠 −3,暗杠 −4,加杠 −1
            n = None
            for m in st:
                t = m["type"]
                if t == "start_kyoku":
                    n = 13
                elif m.get("actor") != s:
                    continue
                elif t == "tsumo":
                    n += 1
                elif t == "dahai":
                    n -= 1
                elif t in ("chi", "pon"):
                    n -= 2
                elif t == "daiminkan":
                    n -= 3
                elif t == "ankan":
                    n -= 4
                elif t == "kakan":
                    n -= 1
                if t in ("dahai", "chi", "pon", "daiminkan"):
                    assert n % 3 in (1, 2) and 1 <= n <= 14


def test_reaction_mapping():
    game = Game(seed=5)
    legal = game.legal_actions()
    discard = next(a for a in legal if a.type == A.ActionType.DISCARD)
    r = {"type": "dahai", "actor": game.current, "pai": tile_to_mjai(discard.arg), "tsumogiri": False}
    assert reaction_to_action(r, game) == discard
    assert reaction_to_action(None, game) is None
    assert reaction_to_action({"type": "none"}, game) is None  # 自己回合不能过


def test_mortal_index_table_covers_all_ids():
    covered = {a.id for i in range(MORTAL_ACTIONS) for a in mortal_index_to_actions(i)}
    assert covered == set(range(A.NUM_ACTIONS))  # 本项目每个动作都能从 Mortal 的某个动作换算过来


@pytest.mark.skipif(not (MORTAL_DIR / "inference.py").is_file(), reason="本机没有装 Mortal")
def test_play_with_mortal_has_no_mismatch():
    from riichi_ai.mortal import play

    game, stats = play(30_000_123, ["mortal", "shanten", "shanten", "shanten"])
    assert game.is_over
    assert stats.errors == 0 and stats.mismatches == 0 and stats.decisions > 30

"""对局不变量检查。测试和长跑脚本(tools/riichi_soak.py)共用,出错时抛 AssertionError。"""
from __future__ import annotations

from .game import NUM_SEATS, NUM_TILES, Game, Phase
from .tiles import NUM_TILE_CODES, full_wall


def check_step(game: Game) -> None:
    """任何时刻都要成立的条件。"""
    cfg = game.config
    # 点数守恒: 桌上的立直棒也算
    assert sum(game.scores) + 1000 * game.sticks == cfg.start_points * NUM_SEATS, (game.scores, game.sticks)
    if game.is_over:
        assert game.sticks == 0
        return
    # 牌数守恒: 每张具体的牌(含赤牌)恰好出现一次
    seen = [0] * NUM_TILE_CODES
    for t in game.wall[game.draw_pos : NUM_TILES - game.kan_total]:
        seen[t] += 1
    for s in range(NUM_SEATS):
        for t in game.hand_tiles(s):
            seen[t] += 1
        for m in game.melds[s]:
            for t in m.tiles:
                seen[t] += 1
        for t, flags in zip(game.discards[s], game.discard_flags[s]):
            if not flags[2]:  # 被吃碰杠走的那张已经算在副露里
                seen[t] += 1
    if game.phase == Phase.ROB_KAN and game.pending[2] == "kakan":
        seen[game.pending[1]] += 1  # 加杠宣言的那张,正在等抢杠
    expected = [0] * NUM_TILE_CODES
    for t in full_wall(cfg.aka):
        expected[t] += 1
    assert seen == expected, [(i, a, b) for i, (a, b) in enumerate(zip(seen, expected)) if a != b]
    # 手牌张数
    for s in range(NUM_SEATS):
        size = sum(game.hands[s])
        base = 13 - 3 * len(game.melds[s])
        turn = game.phase in (Phase.TURN, Phase.RIICHI) and s == game.current
        assert size == base + (1 if turn else 0), (s, size, game.phase)
        assert all(0 <= n <= 4 for n in game.hands[s])
    assert 0 <= game.wall_remaining <= 70
    assert game.kan_total <= 4 and game.dora_revealed <= 5
    # 立直的人一定门清
    for s in range(NUM_SEATS):
        if game.riichi[s]:
            assert game.is_menzen(s)
    legal = game.legal_actions()
    assert legal, "轮到某人时必须至少有一个合法动作"


def check_final(game: Game) -> None:
    """一场结束后。"""
    assert game.is_over and game.current == -1 and not game.legal_actions()
    assert sum(game.scores) == game.config.start_points * NUM_SEATS
    assert abs(sum(game.final_points())) < 1e-9
    assert sorted(game.ranks()) == [0, 1, 2, 3]
    for r in game.hand_results:
        if r["type"] == "win":
            # 一局的点数变化之和 = 和牌者拿走的供托(立直棒在宣言时已经扣过)
            assert sum(r["deltas"]) == sum(w["sticks"] for w in r["wins"])
            for w in r["wins"]:
                assert w["yakuman"] or w["han"] >= 1
                assert w["gain"] > 0
        else:
            assert sum(r["deltas"]) == 0
            assert r["reason"] in (
                "exhaustive",
                "nagashi_mangan",
                "kyuushu",
                "suufon_renda",
                "suukaikan",
                "suucha_riichi",
                "sanchahou",
            )
    assert game.end_reason in ("finished", "dealer_top", "tobi", "overtime_target", "overtime_over", "one_hand")

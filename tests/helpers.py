"""测试辅助: 直接摆出一个局面,不用从发牌开始凑。"""
from __future__ import annotations

from dataclasses import replace
from typing import List, Optional, Sequence

from chuanma import Game, Meld, MeldType, RuleConfig
from chuanma.game import Phase
from chuanma.tiles import NUM_TILE_TYPES, full_wall, parse_tile, parse_tiles, tiles_to_counts

# 一手离听牌很远、没有对子的废牌(13 张,只有万和筒)
JUNK = "12345689m13579p"

MAN, PIN, SOU = 0, 1, 2


def pong(tile: str, from_seat: int = 0) -> Meld:
    return Meld(MeldType.PONG, parse_tile(tile), from_seat)


def gang(tile: str, kind: MeldType = MeldType.MING_GANG, from_seat: int = 0) -> Meld:
    return Meld(kind, parse_tile(tile), from_seat)


def make_game(
    hands: Sequence[str],
    turn: int = 0,
    wall: str = "",
    voids: Sequence[int] = (SOU, SOU, SOU, SOU),
    melds: Optional[Sequence[Sequence[Meld]]] = None,
    drawn: Optional[str] = None,
    config: Optional[RuleConfig] = None,
    dealer: int = 0,
    mid_game: bool = True,
    after_gang: bool = False,
) -> Game:
    """摆一个轮到 turn 座位行动的局面。

    hands: 四家手牌(紧凑写法)。轮到的那家要包含刚摸的牌,即 14 - 3*副露数 张。
    wall: 剩余牌墙,从左到右依次被摸走。
    mid_game: True 表示牌局已进行了一阵(不会触发天胡/地胡)。
    """
    cfg = replace(config or RuleConfig(), exchange_three=False)
    game = Game(config=cfg, seed=0, dealer=dealer)
    game.hands = [tiles_to_counts(parse_tiles(h)) for h in hands]
    game.wall = parse_tiles(wall)
    game.wall_pos = 0
    game.void = list(voids)
    game.melds = [list(m) for m in melds] if melds else [[] for _ in range(4)]
    game.any_meld = any(game.melds)
    game.discards_made = [1, 1, 1, 1] if mid_game else [0, 0, 0, 0]
    game.history = []
    game.events = []
    game._start_turn(turn, drawn=parse_tile(drawn) if drawn else None, after_gang=after_gang)
    assert game.phase == Phase.TURN
    return game


def build_wall(hands: Sequence[str], dealer_extra: str, draws: str = "", dealer: int = 0) -> List[int]:
    """造一副完整的 108 张牌墙: 四家各 13 张起手牌 + 庄家第 14 张 + 指定的摸牌顺序,其余随意。"""
    pool = tiles_to_counts(full_wall())

    def take(text: str) -> List[int]:
        tiles = parse_tiles(text)
        for t in tiles:
            pool[t] -= 1
            assert pool[t] >= 0, "同一种牌用了超过 4 张"
        return tiles

    dealt: List[int] = []
    for h in hands:
        tiles = take(h)
        assert len(tiles) == 13
        dealt.extend(tiles)
    extra = take(dealer_extra)
    assert len(extra) == 1
    drawn = take(draws)
    rest = [t for t in range(NUM_TILE_TYPES) for _ in range(pool[t])]
    return dealt + extra + drawn + rest


def assert_tiles_conserved(game: Game) -> None:
    """每种牌在 牌墙 + 手牌 + 副露 + 弃牌 (+ 换牌途中 / 抢杠途中) 里合计恰好 4 张。"""
    counts = [0] * NUM_TILE_TYPES
    for t in game.wall[game.wall_pos :]:
        counts[t] += 1
    for seat in range(4):
        for t, n in enumerate(game.hands[seat]):
            counts[t] += n
        for m in game.melds[seat]:
            counts[m.tile] += m.size
        for t in game.discards[seat]:
            counts[t] += 1
        if not game.exchange_done:
            for t in game.exchange_out[seat]:
                counts[t] += 1
    if game.phase == Phase.ROB_KONG:
        counts[game.rob_tile] += 1
    assert counts == [4] * NUM_TILE_TYPES, counts

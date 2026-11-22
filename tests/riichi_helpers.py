"""日麻测试辅助: 摆牌墙、造副露、按脚本走几步。"""
from __future__ import annotations

from typing import List, Optional, Sequence

from riichi import Game, RuleConfig
from riichi import actions as A
from riichi.game import NUM_TILES
from riichi.scoring import Meld, MeldType, WinContext, evaluate
from riichi.tiles import full_wall, kind_of, parse_tile, parse_tiles, tiles_to_counts

ONE = RuleConfig(length="one")  # 只打一局,结束就停


def build_wall(
    hands: Sequence[str],
    draws: str = "",
    dora: str = "",
    rinshan: str = "",
    ura: str = "",
    aka: bool = True,
) -> List[int]:
    """造一副 136 张的牌墙。

    hands: 四家的 13 张配牌(座位 0..3)。
    draws: 从第一次摸牌起依次摸到的牌(庄家先摸)。
    dora / ura: 依次是第 1、2… 张宝牌 / 里宝指示牌。
    rinshan: 依次是第 1、2… 张岭上牌。
    其余位置用剩下的牌按固定顺序填。
    """
    pool = full_wall(aka)
    wall: List[Optional[int]] = [None] * NUM_TILES

    def take(text: str) -> List[int]:
        out = []
        for t in parse_tiles(text):
            if t in pool:
                pool.remove(t)
            else:
                raise ValueError(f"牌不够: {text}")
            out.append(t)
        return out

    for s, h in enumerate(hands):
        tiles = take(h)
        assert len(tiles) == 13, f"座位 {s} 的配牌不是 13 张"
        wall[s * 13 : s * 13 + 13] = tiles
    for i, t in enumerate(take(draws)):
        wall[52 + i] = t
    for i, t in enumerate(take(rinshan)):
        wall[135 - i] = t
    for i, t in enumerate(take(dora)):
        wall[130 - 2 * i] = t
    for i, t in enumerate(take(ura)):
        wall[131 - 2 * i] = t
    # 剩下的位置: 先填王牌,再从牌墙末尾往前填,让"依次摸到"的牌尽量是指定的那些
    for i in range(NUM_TILES):
        if wall[i] is None:
            wall[i] = pool.pop()
    return wall  # type: ignore[return-value]


def make(hands, draws="", dora="", rinshan="", ura="", config=ONE, aka=True) -> Game:
    """用指定牌墙开一场(默认只打一局)。"""
    if config is ONE and not aka:
        config = RuleConfig(length="one", aka=False)
    return Game(config=config, walls=[build_wall(hands, draws, dora, rinshan, ura, aka)])


def act(game: Game, seat: int, action) -> None:
    """断言轮到 seat,再执行动作。action 可以是 Action 或者紧凑写法的一张牌(表示打这张)。"""
    assert game.current == seat, f"现在轮到 {game.current},不是 {seat}"
    if isinstance(action, str):
        action = A.discard(parse_tile(action))
    game.step(action)


def legal(game: Game) -> set:
    return set(game.legal_actions())


# 三手离听牌很远、互相吃碰不到的废牌(13 张,同门之间至少隔 3)
J1 = "147m258p369s1357z"
J2 = "258m369p147s2467z"
J3 = "369m147p258s1357z"
# 一手听 1s / 4s 的牌(立直 + 平和)
TENPAI = "123m456p789s23s55p"


def position(
    hands: Sequence[str],
    turn: int = 0,
    drawn: Optional[str] = None,
    draws: str = "",
    melds=None,
    config: RuleConfig = ONE,
    mid: bool = True,
    dora: str = "",
    ura: str = "",
    scores=None,
) -> Game:
    """直接摆一个局面: 四家手牌、轮到谁、刚摸的牌、之后依次摸到的牌。

    轮到的那家手牌要包含刚摸的牌(14 - 3*副露数 张);drawn 为 None 表示刚吃碰完、还没出牌。
    mid=True 表示牌局已经进行了一阵(不会有天和、地和、双立直、九种九牌、四风连打)。
    这个函数不保证牌数守恒,只用于规则用例。
    """
    from riichi.tiles import count_reds

    g = Game(config=config, seed=1)
    for s, h in enumerate(hands):
        tiles = parse_tiles(h)
        g.hands[s] = tiles_to_counts(tiles)
        g.reds[s] = count_reds(tiles)
    if melds:
        g.melds = [list(m) for m in melds]
        g.no_calls = not any(melds)
    g.discards_made = [2] * 4 if mid else [0] * 4
    for i, t in enumerate(parse_tiles(draws)):
        g.wall[g.draw_pos + i] = t
    if dora:
        g.wall[130] = parse_tile(dora)
    if ura:
        g.wall[131] = parse_tile(ura)
    if scores:
        g.scores = list(scores)
    g.current = turn
    g.drawn = parse_tile(drawn) if drawn else None
    g.after_kan = False
    g._legal_cache = None
    return g


def tsumogiri(game: Game, seat: int) -> None:
    """摸什么打什么。"""
    assert game.current == seat and game.drawn is not None
    game.step(A.discard(game.drawn))


def last_wins(game: Game):
    r = game.hand_results[-1]
    assert r["type"] == "win", r
    return r["wins"]


# ---------------------------------------------------------------- 算分用


def chi(text: str, from_seat: int = 3) -> Meld:
    ts = tuple(parse_tiles(text))
    return Meld(MeldType.CHI, ts, ts[0], from_seat)


def pon(text: str, from_seat: int = 1) -> Meld:
    ts = tuple(parse_tiles(text))
    return Meld(MeldType.PON, ts, ts[0], from_seat)


def kan(text: str, kind: MeldType = MeldType.DAIMINKAN, from_seat: int = 1) -> Meld:
    ts = tuple(parse_tiles(text))
    if kind == MeldType.ANKAN:
        return Meld(kind, ts)
    return Meld(kind, ts, ts[0], from_seat)


def value(hand: str, win: str, melds=(), config: Optional[RuleConfig] = None, dora: int = 0, **ctx):
    """算一手牌的价值。hand 是手里的牌,包含和的那张;赤宝牌按牌面自动数。"""
    tiles = parse_tiles(hand)
    aka = sum(1 for t in tiles if t >= 34) + sum(1 for m in melds for t in m.tiles if t >= 34)
    c = WinContext(dora=dora, aka=aka, **ctx)
    return evaluate(tiles_to_counts(tiles), list(melds), kind_of(parse_tile(win)), c, config)


def names(v) -> set:
    return {n for n, _ in v.yaku}

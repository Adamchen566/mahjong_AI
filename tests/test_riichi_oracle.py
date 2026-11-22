"""和独立算分来源对照: PyPI 上的 `mahjong` 库(日麻算分)。

随机对局里每一次"这手牌能不能和、值多少"的判断(包括因为没役不能和的),都拿同样的牌和场况
交给 mahjong 库再算一遍,比较 有没有役、番、符、点数。

mahjong 库不在项目依赖里,装在仓库里的 .venv-riichi 虚拟环境:

    .venv-riichi\\Scripts\\python -m pytest tests/test_riichi_oracle.py

没装时整个文件跳过。对局数由环境变量 RIICHI_ORACLE_GAMES 控制(默认 40 场半庄)。
"""
import os
from collections import Counter

import pytest

mahjong = pytest.importorskip("mahjong")

from mahjong.constants import EAST  # noqa: E402
from mahjong.hand_calculating.hand import HandCalculator  # noqa: E402
from mahjong.hand_calculating.hand_config import HandConfig, HandConstants, OptionalRules  # noqa: E402
from mahjong.meld import Meld as LibMeld  # noqa: E402

from riichi import Game, RandomAgent, ShantenAgent  # noqa: E402
from riichi.scoring import MeldType, ron_points, tsumo_points  # noqa: E402
from riichi.tiles import kind_of  # noqa: E402

ORACLE_GAMES = int(os.environ.get("RIICHI_ORACLE_GAMES", "40"))

OPTIONS = OptionalRules(
    has_open_tanyao=True,
    has_aka_dora=True,
    has_double_yakuman=False,
    kazoe_limit=HandConstants.KAZOE_LIMITED,
    kiriage=False,
    fu_for_open_pinfu=True,
    fu_for_pinfu_tsumo=False,
)
_LIB_TYPES = {
    MeldType.CHI: LibMeld.CHI,
    MeldType.PON: LibMeld.PON,
    MeldType.DAIMINKAN: LibMeld.KAN,
    MeldType.ANKAN: LibMeld.KAN,
    MeldType.KAKAN: LibMeld.SHOUMINKAN,
}


class Allocator:
    """把本引擎的牌编号换成 mahjong 库的 136 编号(种类 * 4 + 第几张;赤 5 是第 0 张)。"""

    def __init__(self):
        self.used = Counter()

    def __call__(self, tile: int) -> int:
        k = kind_of(tile)
        if tile >= 34:
            return k * 4
        start = 1 if k in (4, 13, 22) else 0
        i = start + self.used[k]
        self.used[k] += 1
        assert i < 4, "同一种牌超过 4 张"
        return k * 4 + i


def library_value(game: Game, seat: int, tile: int, tsumo: bool, chankan=False, houtei=False):
    counts, win_kind, ctx = game._win_context(seat, tile, tsumo, chankan, houtei)
    alloc = Allocator()
    melds = []
    meld_ids = []
    for m in game.melds[seat]:
        ids = [alloc(t) for t in m.tiles]
        meld_ids += ids
        opened = m.type != MeldType.ANKAN
        melds.append(LibMeld(meld_type=_LIB_TYPES[m.type], tiles=ids, opened=opened))
    # 手里的牌: 把和的那张单独分配,好把它作为 win_tile 传进去
    hand = game.hand_tiles(seat)
    if tsumo:
        hand.remove(tile)
    win_id = alloc(tile)
    hand_ids = [alloc(t) for t in hand]
    tiles = hand_ids + [win_id] + meld_ids
    indicators = [alloc_indicator(t, tiles) for t in game.dora_indicators()]
    ura = [alloc_indicator(t, tiles + indicators) for t in game.ura_indicators()] if ctx.riichi else []
    config = HandConfig(
        is_tsumo=tsumo,
        is_riichi=ctx.riichi == 1,
        is_daburu_riichi=ctx.riichi == 2,
        is_ippatsu=ctx.ippatsu,
        is_rinshan=ctx.rinshan,
        is_chankan=ctx.chankan,
        is_haitei=ctx.haitei,
        is_houtei=ctx.houtei,
        is_tenhou=ctx.tenhou,
        is_chiihou=ctx.chiihou,
        player_wind=EAST + ctx.seat_wind,
        round_wind=EAST + ctx.round_wind,
        options=OPTIONS,
    )
    return HandCalculator.estimate_hand_value(
        tiles, win_id, melds=melds, dora_indicators=indicators, config=config, ura_dora_indicators=ura
    )


def alloc_indicator(tile: int, taken):
    """宝牌指示牌只影响种类,挑一个没被手牌占用的 136 编号就行。"""
    k = kind_of(tile)
    for i in range(4):
        if k * 4 + i not in taken:
            return k * 4 + i
    return k * 4


def compare(game: Game, seat, tile, tsumo, chankan, houtei, mine, stats):
    lib = library_value(game, seat, tile, tsumo, chankan, houtei)
    where = f"seat={seat} tile={tile} tsumo={tsumo} hand={game.hand_tiles(seat)} melds={game.melds[seat]}"
    if mine is None:
        assert lib.error is not None, f"本引擎判没役,库算出 {lib.han} 番 {lib.yaku}: {where}"
        stats["no_yaku"] += 1
        return
    assert lib.error is None, f"本引擎算出 {mine.yaku},库报错 {lib.error}: {where}"
    dealer = game.seat_wind(seat) == 0
    if mine.yakuman:
        assert lib.han == 13 * mine.yakuman, f"役满倍数不同: {mine.yaku} vs {lib.yaku}: {where}"
        stats["yakuman"] += 1
    else:
        assert (mine.han, mine.fu) == (lib.han, lib.fu), f"{mine.han}番{mine.fu}符 {mine.yaku} vs 库 {lib.han}番{lib.fu}符 {lib.yaku}: {where}"
    if tsumo:
        if dealer:
            assert tsumo_points(mine.base, True, False) == lib.cost["main"], where
        else:
            assert tsumo_points(mine.base, False, True) == lib.cost["main"], where
            assert tsumo_points(mine.base, False, False) == lib.cost["additional"], where
    else:
        assert ron_points(mine.base, dealer) == lib.cost["main"], where
    stats["checked"] += 1
    for name, _ in mine.yaku:
        stats["yaku:" + name.split(" ")[0]] += 1


class CallingAgent:
    """规则型策略的变体: 一半概率吃碰杠,好让副露、杠、岭上、抢杠多出现。"""

    def __init__(self, seed):
        self.base = ShantenAgent(seed)
        self.rnd = RandomAgent(seed)

    def act(self, obs, legal):
        from riichi.actions import ActionType as T

        wins = [a for a in legal if a.type in (T.TSUMO, T.RON)]
        if wins:
            return wins[0]
        calls = [a for a in legal if a.type in (T.CHI, T.PON, T.DAIMINKAN, T.ANKAN, T.KAKAN)]
        if calls and self.rnd.rng.random() < 0.5:
            return self.rnd.rng.choice(calls)
        return self.base.act(obs, legal)


@pytest.mark.parametrize("agent_cls", [ShantenAgent, CallingAgent])
def test_against_mahjong_library(agent_cls, monkeypatch):
    stats = Counter()
    original = Game._win_value

    def checked(self, seat, tile, tsumo, chankan=False, houtei=False):
        mine = original(self, seat, tile, tsumo, chankan=chankan, houtei=houtei)
        compare(self, seat, tile, tsumo, chankan, houtei, mine, stats)
        return mine

    monkeypatch.setattr(Game, "_win_value", checked)
    games = ORACLE_GAMES if agent_cls is ShantenAgent else max(1, ORACLE_GAMES // 4)
    agents = [agent_cls(7 + s) for s in range(4)]
    for seed in range(games):
        game = Game(seed=10_000 + seed, record_events=False)
        while not game.is_over:
            s = game.current
            game.step(agents[s].act(game.observation(s), game.legal_actions()))
    print(f"\n对照 {agent_cls.__name__}: {dict(sorted(stats.items()))}")
    if agent_cls is ShantenAgent and games >= 20:
        assert stats["checked"] > 100

"""和独立算分来源对照(二): 随机造和牌,覆盖对局里很少出现的役。

偏向清一色、字牌、幺九、绿一色、九莲宝灯来造牌,再加七对子和国士无双。
每一手都交给本引擎的 evaluate() 和 mahjong 库各算一遍,比较 有没有役、番、符(役满比倍数)。
手数由环境变量 RIICHI_ORACLE_HANDS 控制(默认 20000)。没装 mahjong 库时跳过。
"""
import os
import random
from collections import Counter

import pytest

pytest.importorskip("mahjong")

from mahjong.constants import EAST  # noqa: E402
from mahjong.hand_calculating.hand import HandCalculator  # noqa: E402
from mahjong.hand_calculating.hand_config import HandConfig  # noqa: E402
from mahjong.meld import Meld as LibMeld  # noqa: E402

from riichi.scoring import Meld, MeldType, WinContext, evaluate  # noqa: E402
from riichi.tiles import YAOCHU, dora_of, kind_of  # noqa: E402
from test_riichi_oracle import _LIB_TYPES, OPTIONS, Allocator, alloc_indicator  # noqa: E402

_MODES = ("any", "flush", "honors", "yaochu", "green", "chuuren")


def _random_win(rng: random.Random):
    """随机造一手和了的牌: (手里的牌含和的那张, 副露, 和的那张, 是否自摸)。"""
    mode = rng.choice(_MODES)
    suit = rng.randrange(3)
    if mode == "any":
        kinds = list(range(34))
    elif mode == "flush":
        kinds = list(range(suit * 9, suit * 9 + 9)) + (list(range(27, 34)) if rng.random() < 0.5 else [])
    elif mode == "honors":
        kinds = list(range(27, 34)) + ([suit * 9, suit * 9 + 8] if rng.random() < 0.3 else [])
    elif mode == "yaochu":
        kinds = list(YAOCHU)
    elif mode == "green":
        kinds = [19, 20, 21, 23, 25, 32]
    else:
        kinds = list(range(suit * 9, suit * 9 + 9))
    counts = [0] * 34
    groups = []
    for _ in range(200):
        if len(groups) == 4:
            break
        k = rng.choice(kinds)
        if rng.random() < 0.5 and k < 27 and k % 9 <= 6 and k + 1 in kinds and k + 2 in kinds:
            if all(counts[k + i] < 4 for i in range(3)):
                for i in range(3):
                    counts[k + i] += 1
                groups.append(("chi", k))
        elif counts[k] == 0:
            counts[k] += 3
            groups.append(("pon", k))
    if len(groups) < 4:
        return None
    pair_options = [k for k in kinds if counts[k] <= 2]
    if not pair_options:
        return None
    pair = rng.choice(pair_options)
    counts[pair] += 2
    reds_left = {4: True, 13: True, 22: True}

    def tiles_of(kind_list):
        out = []
        for k in kind_list:
            if reds_left.get(k) and rng.random() < 0.3:
                reds_left[k] = False
                out.append(34 + k // 9)
            else:
                out.append(k)
        return out

    melds = []
    concealed = [pair, pair]
    for typ, k in groups:
        r = rng.random()
        if typ == "chi":
            if r < 0.3:
                ts = tiles_of([k, k + 1, k + 2])
                melds.append(Meld(MeldType.CHI, tuple(ts), ts[0], 3))
            else:
                concealed += [k, k + 1, k + 2]
        elif r < 0.15:
            ts = tiles_of([k] * 3)
            melds.append(Meld(MeldType.PON, tuple(ts), ts[0], 1))
        elif r < 0.27 and counts[k] == 3:
            kind = rng.choice((MeldType.DAIMINKAN, MeldType.ANKAN, MeldType.KAKAN))
            ts = tiles_of([k] * 4)
            melds.append(Meld(kind, tuple(ts)) if kind == MeldType.ANKAN else Meld(kind, tuple(ts), ts[0], 2))
            counts[k] += 1
        else:
            concealed += [k] * 3
    if max(counts) > 4:
        return None
    concealed = tiles_of(concealed)
    return concealed, melds, rng.choice(concealed), rng.random() < 0.5


def _special_win(rng: random.Random):
    """七对子或国士无双。"""
    if rng.random() < 0.3:
        concealed = list(YAOCHU) + [rng.choice(YAOCHU)]
    else:
        pool = rng.choice([list(range(34)), list(range(27, 34)), list(YAOCHU), list(range(9)) + list(range(27, 34))])
        concealed = [k for k in rng.sample(pool, 7) for _ in range(2)]
    return concealed, [], rng.choice(concealed), rng.random() < 0.5


def _compare(rng: random.Random, stats: Counter) -> None:
    made = _special_win(rng) if rng.random() < 0.15 else _random_win(rng)
    if made is None:
        return
    concealed, melds, win, tsumo = made
    menzen = all(m.type == MeldType.ANKAN for m in melds)
    has_kan = any(m.is_kan for m in melds)
    riichi = rng.choice((0, 1, 1, 2)) if menzen else 0
    first = not melds and riichi == 0 and tsumo and rng.random() < 0.05
    ctx = WinContext(
        tsumo=tsumo,
        riichi=riichi,
        ippatsu=bool(riichi) and rng.random() < 0.3,
        rinshan=tsumo and has_kan and rng.random() < 0.3,
        chankan=(not tsumo) and rng.random() < 0.05,
        seat_wind=rng.randrange(4),
        round_wind=rng.randrange(2),
    )
    if ctx.rinshan:
        ctx.ippatsu = False  # 开杠会让一发消失
    if first:
        ctx.tenhou = rng.random() < 0.5
        ctx.chiihou = not ctx.tenhou
        ctx.seat_wind = 0 if ctx.tenhou else rng.randrange(1, 4)
    if tsumo and not ctx.rinshan and rng.random() < 0.05:
        ctx.haitei = True
    if not tsumo and not ctx.chankan and rng.random() < 0.05:
        ctx.houtei = True
    counts = [0] * 34
    for t in concealed:
        counts[kind_of(t)] += 1
    total = list(counts)
    all_tiles = list(concealed)
    for m in melds:
        for t in m.tiles:
            total[kind_of(t)] += 1
            all_tiles.append(t)
    if any(all_tiles.count(k) == 4 for k in (4, 13, 22)):
        return  # 有赤牌的牌里不可能有 4 张普通 5
    indicators = [rng.randrange(34) for _ in range(rng.randrange(1, 4))]
    uras = [rng.randrange(34) for _ in indicators] if riichi else []
    ctx.dora = sum(total[dora_of(i)] for i in indicators)
    ctx.ura = sum(total[dora_of(i)] for i in uras)
    ctx.aka = sum(1 for t in all_tiles if t >= 34)
    mine = evaluate(counts, melds, kind_of(win), ctx)

    alloc = Allocator()
    lib_melds, meld_ids = [], []
    for m in melds:
        ids = [alloc(t) for t in m.tiles]
        meld_ids += ids
        lib_melds.append(LibMeld(meld_type=_LIB_TYPES[m.type], tiles=ids, opened=m.type != MeldType.ANKAN))
    rest = list(concealed)
    rest.remove(win)
    win_id = alloc(win)
    tiles = [alloc(t) for t in rest] + [win_id] + meld_ids
    config = HandConfig(
        is_tsumo=tsumo,
        is_riichi=riichi == 1,
        is_daburu_riichi=riichi == 2,
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
    lib = HandCalculator.estimate_hand_value(
        tiles,
        win_id,
        melds=lib_melds,
        dora_indicators=[alloc_indicator(i, tiles) for i in indicators],
        config=config,
        ura_dora_indicators=[alloc_indicator(i, tiles) for i in uras],
    )
    where = f"{concealed} 副露 {melds} 和 {win} {ctx}"
    if mine is None:
        assert lib.error is not None, f"本引擎判没役,库算出 {lib.han}番 {lib.yaku}: {where}"
        stats["(没役)"] += 1
        return
    assert lib.error is None, f"本引擎 {mine.yaku},库报错 {lib.error}: {where}"
    if mine.yakuman:
        assert lib.han == 13 * mine.yakuman, f"{mine.yaku} vs {lib.yaku}: {where}"
    else:
        assert (mine.han, mine.fu) == (lib.han, lib.fu), (
            f"{mine.han}番{mine.fu}符 {mine.yaku} vs {lib.han}番{lib.fu}符 {lib.yaku}: {where}"
        )
    stats["(核对)"] += 1
    for name, _ in mine.yaku:
        stats[name.split(" ")[0]] += 1


RARE = (
    "国士无双", "四暗刻", "大三元", "小四喜", "大四喜", "字一色", "绿一色", "清老头", "九莲宝灯",
    "四杠子", "天和", "地和", "清一色", "混老头", "小三元", "三杠子", "二杯口", "纯全带幺九",
    "三色同刻", "对对和", "岭上开花", "抢杠", "海底摸月", "河底捞鱼", "双立直",
)


def test_constructed_hands_against_library():
    rng = random.Random(2026)
    stats = Counter()
    for _ in range(int(os.environ.get("RIICHI_ORACLE_HANDS", "20000"))):
        _compare(rng, stats)
    print(f"\n随机和牌对照: {dict(sorted(stats.items()))}")
    missing = [name for name in RARE if not stats[name]]
    assert not missing, f"没覆盖到 {missing}"

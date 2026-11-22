"""牌理: 从一个座位自己的视图算出向听数、进张、听哪些牌。

只读这个座位看得到的东西(自己的手牌、所有人的副露和弃牌),所以可以放心地显示给玩家。
全部是规则计算,不需要模型。

    13 张型(没轮到自己出牌)  现在几向听;没听牌时列出进张,听牌时列出能胡的牌和番数
    14 张型(轮到自己出牌)    每一张能打的牌: 打出去之后几向听、进张或听的牌

"剩几张"指这个座位还没见过的张数: 4 减去自己手里的、所有副露里的、所有弃牌里的。
它们可能在牌墙里,也可能在别人手里。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .config import RuleConfig
from .fan import Meld, MeldType, WinContext, evaluate_fan
from .hand import winning_tiles
from .shanten import shanten, useful_tiles
from .tiles import COPIES, NUM_RANKS, NUM_TILE_TYPES, tiles_to_counts

_RON = WinContext(zimo=False)
_GANG_TYPES = ("MING_GANG", "AN_GANG", "JIA_GANG")
_PLAYING = ("TURN", "RESPONSE", "ROB_KONG")


def unseen_counts(obs: Dict[str, Any]) -> List[int]:
    """每种牌这个座位还没见过几张。"""
    seen = tiles_to_counts(obs["hand"])
    for row in obs["melds"]:
        for m in row:
            if m["tile"] is not None:
                seen[m["tile"]] += 4 if m["type"] in _GANG_TYPES else 3
    for pile in obs["discards"]:
        for t in pile:
            seen[t] += 1
    return [max(0, COPIES - n) for n in seen]


def true_shanten(counts: Sequence[int], num_melds: int, void_suit: int) -> int:
    """向听数,把"缺门牌必须先打完"也算进去。

    shanten() 把缺门牌当废牌,但默认废牌随时能换成有用的牌。手里的缺门牌多到
    "牌型已经差不多了,只是缺门还没打完"时,它会少算: 每打掉一张缺门牌都要花一巡。
    13 张型里有 v 张缺门牌,至少还要 v 巡才能听牌;14 张型(马上能打掉一张)是 v - 1。
    """
    base = shanten(counts, num_melds, void_suit)
    if void_suit < 0:
        return base
    v = sum(counts[void_suit * NUM_RANKS : (void_suit + 1) * NUM_RANKS])
    if v == 0:
        return base
    waiting_to_discard = sum(counts) % 3 == 2
    return max(base, v - 1 if waiting_to_discard else v)


def insight(obs: Dict[str, Any], config: Optional[RuleConfig] = None) -> Optional[Dict[str, Any]]:
    """这个座位现在的牌理。换三张、定缺阶段,或者已经胡了,返回 None。"""
    seat = obs["seat"]
    if obs["phase"] not in _PLAYING or obs["won"][seat]:
        return None
    config = config or RuleConfig()
    counts = tiles_to_counts(obs["hand"])
    void = obs["void"][seat]
    void = -1 if void is None else void
    melds = [Meld(MeldType[m["type"]], m["tile"], m["from_seat"]) for m in obs["melds"][seat]]
    left = unseen_counts(obs)
    void_left = 0 if void < 0 else sum(counts[void * NUM_RANKS : (void + 1) * NUM_RANKS])

    out: Dict[str, Any] = {"void_left": void_left}
    if sum(counts) % 3 == 2:  # 轮到自己出牌
        tiles = [t for t in range(NUM_TILE_TYPES) if counts[t]]
        if void_left:
            tiles = [t for t in tiles if t // NUM_RANKS == void]  # 缺门没打完时只能打缺门
        options = []
        for t in tiles:
            counts[t] -= 1
            options.append({"tile": t, **_thirteen(counts, melds, void, left, config)})
            counts[t] += 1
        best = min(o["shanten"] for o in options)
        most = max(o["total"] for o in options if o["shanten"] == best)
        for o in options:
            o["best"] = o["shanten"] == best and o["total"] == most
        out["shanten"] = best
        out["discards"] = options
    else:
        out.update(_thirteen(counts, melds, void, left, config))
    return out


def _thirteen(
    counts: List[int], melds: List[Meld], void: int, left: List[int], config: RuleConfig
) -> Dict[str, Any]:
    """13 张型: 几向听,以及进张(没听牌)或能胡的牌(听牌)。"""
    num_melds = len(melds)
    s = true_shanten(counts, num_melds, void)
    if s == 0:
        meld_tiles = [m.tile for m in melds for _ in range(m.size)]
        waits = []
        for t in winning_tiles(counts, num_melds, void, meld_tiles):
            counts[t] += 1
            result = evaluate_fan(counts, melds, _RON, config)
            counts[t] -= 1
            waits.append(
                {"tile": t, "left": left[t], "fan": result.capped_fan, "points": result.points, "names": list(result.names)}
            )
        return {"shanten": 0, "waits": waits, "total": sum(w["left"] for w in waits)}
    useful = [{"tile": t, "left": left[t]} for t in useful_tiles(counts, num_melds, void)]
    return {"shanten": s, "useful": useful, "total": sum(u["left"] for u in useful)}

"""危险度: 打出一张牌,被某一家胡(点炮)的可能有多大。

只用出牌这一家自己看得到的东西。做法是统计而不是推理: 让电脑打很多局,
把每一次出牌按下面几个特征分到格子里,数一数每个格子里有多大比例点了炮
(tools/fit_danger.py 生成 danger_table.json)。用的时候查表。

    巡数      那一家已经打了多少张牌(越往后越可能听牌)
    副露      那一家碰、杠了几组
    见过几张  这张牌自己已经见过几张(含手里的;见得越多,别人越难要它)
    现物      那一家自己打过这张牌
    位置      幺九、二八、中张

两条不用查表的规则: 那一家缺这门花色,或者已经胡了,它就一定不会胡这张牌。

这是"和电脑打出来的牌局里的频率",不是对面这三个人手牌的精确推断;
和打法很不一样的人对局时会有偏差。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .tiles import NUM_RANKS, tiles_to_counts

TABLE_PATH = Path(__file__).with_name("danger_table.json")
SHAPE = (4, 4, 4, 2, 3)  # 巡数、副露、见过几张、现物、位置
_GANG_TYPES = ("MING_GANG", "AN_GANG", "JIA_GANG")

Cell = Tuple[int, int, int, int, int]


def seen_counts(obs: Dict[str, Any]) -> List[int]:
    """每种牌这个座位已经见过几张: 自己手里的、所有副露里的、所有弃牌里的。"""
    seen = tiles_to_counts(obs["hand"])
    for row in obs["melds"]:
        for m in row:
            if m["tile"] is not None:
                seen[m["tile"]] += 4 if m["type"] in _GANG_TYPES else 3
    for pile in obs["discards"]:
        for t in pile:
            seen[t] += 1
    return seen


def cell_of(obs: Dict[str, Any], tile: int, opp: int, seen: Optional[List[int]] = None) -> Optional[Cell]:
    """这次出牌对 opp 这一家落在哪个格子。返回 None 表示它一定不会胡这张牌。"""
    if obs["won"][opp] or obs["void"][opp] == tile // NUM_RANKS:
        return None
    seen = seen or seen_counts(obs)
    rank = tile % NUM_RANKS
    position = 0 if rank in (0, 8) else 1 if rank in (1, 7) else 2
    return (
        min(3, len(obs["discards"][opp]) // 4),
        min(3, len(obs["melds"][opp])),
        max(0, min(3, seen[tile] - 1)),
        int(tile in obs["discards"][opp]),
        position,
    )


@lru_cache(maxsize=1)
def load_table() -> Optional[Dict[str, Any]]:
    if not TABLE_PATH.is_file():
        return None
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


def danger(obs: Dict[str, Any], tile: int, seen: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
    """打出 tile 点炮的可能。没有统计表时返回 None。

    返回 {"p": 至少被一家胡的概率, "by": [[座位, 概率], ...]},by 只列不为零的那几家。
    """
    table = load_table()
    if table is None:
        return None
    p = table["p"]
    seen = seen or seen_counts(obs)
    safe = 1.0
    by = []
    for opp in range(4):
        if opp == obs["seat"]:
            continue
        cell = cell_of(obs, tile, opp, seen)
        if cell is None:
            continue
        a, b, c, d, e = cell
        q = p[a][b][c][d][e]
        safe *= 1.0 - q
        by.append([opp, round(q, 4)])
    return {"p": round(1.0 - safe, 4), "by": by}

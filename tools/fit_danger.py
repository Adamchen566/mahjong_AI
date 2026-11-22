"""统计"打出一张牌有多大可能点炮",生成 chuanma/danger_table.json。

    python tools/fit_danger.py --games 40000 --workers 12

让神经网络和规则型程序混着打,记下每一次出牌对每个对手落在哪个格子(见 chuanma/danger.py)、
这一家有没有胡这张牌。五分之一的牌局留出来不参与统计,用来检验表里的概率准不准。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai import make_agent  # noqa: E402
from chuanma import ActionType, Game  # noqa: E402
from chuanma.danger import SHAPE, TABLE_PATH, cell_of, seen_counts  # noqa: E402

SEED0 = 40_000_000  # 不和训练、评估、段位梯用的牌重叠
LINEUPS = (("net", "rule", "net", "rule"), ("net", "net", "net", "net"), ("rule", "net", "rule", "rule"))
_NET = []


def _agent(name, seed):
    if name != "net":
        return make_agent(name, seed)
    if not _NET:
        _NET.append(make_agent("net"))
    return _NET[0]


def play(seed):
    """打一局,返回 {格子: [次数, 点炮次数]}。"""
    lineup = LINEUPS[seed % len(LINEUPS)]
    agents = [_agent(lineup[(s + seed) % 4], seed * 10 + s) for s in range(4)]
    game = Game(seed=seed, dealer=seed % 4)
    counts = {}
    pending = None  # 上一次出牌: (出牌的人, {对手: 格子}, 当时已经有几次胡牌)
    def settle():
        if pending is None:
            return
        seat, cells, before = pending
        hit = {w.seat for w in game.wins[before:] if not w.zimo and w.from_seat == seat}
        for opp, cell in cells.items():
            row = counts.setdefault(cell, [0, 0])
            row[0] += 1
            row[1] += opp in hit
    while not game.is_over:
        seat = game.current
        obs = game.observation(seat)
        action = agents[seat].act(obs, game.legal_actions())
        if action.type == ActionType.DISCARD:
            settle()
            seen = seen_counts(obs)
            cells = {}
            for opp in range(4):
                if opp != seat:
                    cell = cell_of(obs, action.tile, opp, seen)
                    if cell is not None:
                        cells[opp] = cell
            pending = (seat, cells, len(game.wins))
        game.step(action)
    settle()
    return seed, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=40000)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    fit, held = {}, {}
    with Pool(args.workers) as pool:
        for seed, counts in pool.imap_unordered(play, range(SEED0, SEED0 + args.games), chunksize=50):
            into = held if seed % 5 == 0 else fit
            for cell, (n, k) in counts.items():
                row = into.setdefault(cell, [0, 0])
                row[0] += n
                row[1] += k

    total_n = sum(v[0] for v in fit.values())
    total_k = sum(v[1] for v in fit.values())
    base = total_k / total_n
    prior = 200  # 样本少的格子往总体比例上靠
    a, b, c, d, e = SHAPE
    p = [[[[[0.0] * e for _ in range(d)] for _ in range(c)] for _ in range(b)] for _ in range(a)]
    n = [[[[[0] * e for _ in range(d)] for _ in range(c)] for _ in range(b)] for _ in range(a)]
    for i in range(a):
        for j in range(b):
            for k in range(c):
                for m in range(d):
                    for r in range(e):
                        cn, ck = fit.get((i, j, k, m, r), (0, 0))
                        p[i][j][k][m][r] = round((ck + prior * base) / (cn + prior), 5)
                        n[i][j][k][m][r] = cn

    # 检验: 留出的牌局里,按表里的概率分档,看每一档实际点炮的比例
    edges = [0, 0.005, 0.01, 0.02, 0.04, 0.08, 1.01]
    check = []
    for lo, hi in zip(edges, edges[1:]):
        cn = ck = 0
        exp = 0.0
        for cell, (hn, hk) in held.items():
            q = p[cell[0]][cell[1]][cell[2]][cell[3]][cell[4]]
            if lo <= q < hi:
                cn += hn
                ck += hk
                exp += q * hn
        if cn:
            check.append({"from": lo, "to": min(hi, 1), "samples": cn, "predicted": round(exp / cn, 4), "actual": round(ck / cn, 4)})

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "games": args.games,
        "samples": total_n,
        "base_rate": round(base, 5),
        "features": ["那一家打了几张牌 // 4(封顶 3)", "那一家的副露数(封顶 3)", "这张牌已经见过几张 - 1", "那一家打过这张牌", "幺九 / 二八 / 中张"],
        "holdout": check,
        "p": p,
        "n": n,
    }
    TABLE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{args.games} 局,{total_n:,} 次(出牌 × 对手),总体点炮比例 {base:.2%}")
    for row in check:
        print(f"  表里 {row['from']:.1%}–{row['to']:.0%}: 预计 {row['predicted']:.2%},留出的牌局里实际 {row['actual']:.2%}({row['samples']:,} 次)")
    print(f"已写入 {TABLE_PATH}")


if __name__ == "__main__":
    main()

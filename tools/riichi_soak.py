"""日麻引擎长跑验收: 多进程打很多场半庄,每一步都查不变量。

    python tools/riichi_soak.py --agents random -n 10000 -j 12
    python tools/riichi_soak.py --agents shanten -n 10000 -j 12

另外单核测一次速度(不查不变量,和训练时的用法一样):

    python tools/riichi_soak.py --agents shanten --speed 200

出错时打印种子和异常,可以用同一个种子复现。只用 CPU,不碰显卡。
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from riichi import Game, make_agent  # noqa: E402
from riichi.invariants import check_final, check_step  # noqa: E402


def run_chunk(args):
    agent_name, seeds, every_step = args
    stats = Counter()
    failures = []
    for seed in seeds:
        agents = [make_agent(agent_name, seed * 4 + s) for s in range(4)]
        try:
            game = Game(seed=seed, record_events=False)
            while not game.is_over:
                s = game.current
                game.step(agents[s].act(game.observation(s), game.legal_actions()))
                stats["decisions"] += 1
                if every_step:
                    check_step(game)
            check_final(game)
        except Exception:  # noqa: BLE001 - 收集起来一起报告
            failures.append((seed, traceback.format_exc()))
            continue
        stats["games"] += 1
        stats["hands"] += len(game.hand_results)
        stats["end:" + game.end_reason] += 1
        for r in game.hand_results:
            if r["type"] == "win":
                stats["win:" + r["reason"]] += 1
                stats["wins"] += len(r["wins"])
                if len(r["wins"]) > 1:
                    stats["double_ron"] += 1
                for w in r["wins"]:
                    if w["yakuman"]:
                        stats["yakuman"] += 1
            else:
                stats["draw:" + r["reason"]] += 1
    return stats, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", default="shanten")
    parser.add_argument("-n", "--games", type=int, default=1000)
    parser.add_argument("-j", "--jobs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=1_000_000)
    parser.add_argument("--speed", type=int, default=0, help="只在单核上测这么多场的速度,不查不变量")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.speed:
        start = time.perf_counter()
        stats, failures = run_chunk((args.agents, range(args.seed, args.seed + args.speed), False))
        sec = time.perf_counter() - start
        print(
            f"单核 {args.agents}: {stats['games']} 场半庄 {sec:.1f} 秒 = {stats['games'] / sec:.2f} 场/秒,"
            f"{stats['hands'] / sec:.0f} 局/秒,{stats['decisions'] / sec:.0f} 次决策/秒"
        )
        return 1 if failures else 0

    seeds = list(range(args.seed, args.seed + args.games))
    size = max(1, len(seeds) // (args.jobs * 8))
    chunks = [(args.agents, seeds[i : i + size], True) for i in range(0, len(seeds), size)]
    total = Counter()
    failures = []
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for stats, fails in pool.map(run_chunk, chunks):
            total.update(stats)
            failures.extend(fails)
    sec = time.perf_counter() - start
    print(f"{args.agents}: {total['games']} 场半庄,{total['hands']} 局,{sec:.0f} 秒({args.jobs} 进程,每步查不变量)")
    print(f"  出错 {len(failures)} 场")
    for key in sorted(k for k in total if ":" in k):
        print(f"  {key}: {total[key]}")
    print(f"  双响 {total['double_ron']} 次,役满 {total['yakuman']} 次")
    for seed, tb in failures[:5]:
        print(f"\n种子 {seed}:\n{tb}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

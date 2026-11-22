"""日麻同牌对比评估: 同一个种子的半庄打 4 次,待测策略轮流坐 4 个座位,其余三家是基准策略。

    python -m riichi_ai.evaluate --candidate checkpoints/riichi_bc/best.pt --baseline shanten -n 300 --workers 12

指标是待测策略的平均名次分(每场)和 95% 置信区间,另报平均顺位、和了率、放铳率(按局算)。
区间下界大于 0 才算"更强"。
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from typing import Dict, List, Optional, Tuple

from riichi.agents import Agent
from riichi.game import NUM_SEATS, Game

from . import AGENTS, make_agent

EVAL_SEED = 10_000_000  # 评估用的种子,不和模仿数据(0 起)、自我对弈(1 亿起)重叠

_CACHE: Dict[str, Agent] = {}


def _agent(source: str, seed: int) -> Agent:
    """规则类策略每场新建;模型每个进程只加载一次。"""
    if source in AGENTS and source != "net":
        return make_agent(source, seed)
    if source not in _CACHE:
        _CACHE[source] = make_agent(source)
    return _CACHE[source]


@dataclass
class DealResult:
    points: List[float]  # 待测策略坐 0..3 号位时的名次分
    ranks: List[int]
    hands: int = 0
    wins: int = 0
    deal_ins: int = 0
    riichi: int = 0


@dataclass
class EvalResult:
    candidate: str
    baseline: str
    deals: int
    seconds: float
    deal_means: List[float] = field(repr=False, default_factory=list)
    rank_sum: int = 0
    hands: int = 0
    wins: int = 0
    deal_ins: int = 0

    @property
    def games(self) -> int:
        return self.deals * NUM_SEATS

    @property
    def mean(self) -> float:
        return sum(self.deal_means) / len(self.deal_means)

    @property
    def stderr(self) -> float:
        n = len(self.deal_means)
        if n < 2:
            return float("nan")
        m = self.mean
        return math.sqrt(sum((x - m) ** 2 for x in self.deal_means) / (n - 1) / n)

    @property
    def ci95(self) -> Tuple[float, float]:
        h = 1.96 * self.stderr
        return self.mean - h, self.mean + h

    @property
    def avg_rank(self) -> float:
        return self.rank_sum / self.games + 1

    def summary(self) -> str:
        lo, hi = self.ci95
        verdict = "显著更强" if lo > 0 else ("显著更弱" if hi < 0 else "差距不显著")
        return "\n".join(
            [
                f"{self.candidate} 对 3 个 {self.baseline}: {self.deals} 个种子 × 4 个座位 = {self.games} 场半庄,用时 {self.seconds:.0f} 秒",
                f"  平均名次分 {self.mean:+.2f}/场,95% 置信区间 [{lo:+.2f}, {hi:+.2f}] → {verdict}",
                f"  平均顺位 {self.avg_rank:.3f},和了率 {self.wins / max(self.hands, 1):.1%},放铳率 {self.deal_ins / max(self.hands, 1):.1%}(按局)",
            ]
        )


def play_deal(args: Tuple[str, str, int]) -> DealResult:
    candidate, baseline, seed = args
    out = DealResult(points=[], ranks=[])
    for seat in range(NUM_SEATS):
        agents = [_agent(baseline, seed * 10 + s) for s in range(NUM_SEATS)]
        agents[seat] = _agent(candidate, seed * 10 + seat)
        game = Game(seed=seed, record_events=False)
        while not game.is_over:
            s = game.current
            legal = game.legal_actions()
            game.step(legal[0] if len(legal) == 1 else agents[s].act(game.observation(s), legal))
        out.points.append(game.final_points()[seat])
        out.ranks.append(game.ranks()[seat])
        out.hands += len(game.hand_results)
        for r in game.hand_results:
            for w in r.get("wins", []):
                if w["seat"] == seat:
                    out.wins += 1
                elif w["from_seat"] == seat:
                    out.deal_ins += 1
    return out


def evaluate(candidate: str, baseline: str, num_deals: int, seed: int = EVAL_SEED, workers: int = 1) -> EvalResult:
    jobs = [(candidate, baseline, seed + i) for i in range(num_deals)]
    start = time.perf_counter()
    if workers > 1:
        with Pool(workers) as pool:
            deals = pool.map(play_deal, jobs, chunksize=max(1, num_deals // (workers * 4)))
    else:
        deals = [play_deal(j) for j in jobs]
    out = EvalResult(candidate, baseline, num_deals, time.perf_counter() - start)
    for d in deals:
        out.deal_means.append(sum(d.points) / NUM_SEATS)
        out.rank_sum += sum(d.ranks)
        out.hands += d.hands
        out.wins += d.wins
        out.deal_ins += d.deal_ins
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m riichi_ai.evaluate", description="日麻同牌对比评估")
    parser.add_argument("--candidate", default="shanten")
    parser.add_argument("--baseline", default="simple")
    parser.add_argument("-n", "--num-deals", type=int, default=100)
    parser.add_argument("--seed", type=int, default=EVAL_SEED)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(evaluate(args.candidate, args.baseline, args.num_deals, args.seed, args.workers).summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

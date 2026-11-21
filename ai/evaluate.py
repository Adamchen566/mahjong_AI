"""同牌对比评估。

同一副牌(同一个种子)打 4 次,待测策略轮流坐 4 个座位,其余三家是基准策略。
这样发牌的运气被抵消,比较的只是打法。

    python -m ai.evaluate --candidate rule --baseline simple -n 1000 --workers 12

输出待测策略的平均每局得分和 95% 置信区间。区间下界大于 0 才算"更强"。
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from typing import List, Optional, Tuple

from chuanma.config import RuleConfig
from chuanma.game import NUM_SEATS
from chuanma.runner import play_game

from . import AGENTS, make_agent


EVAL_SEED = 10_000_000  # 评估用的牌从这里起,不和生成训练数据用的种子重叠


@dataclass
class DealResult:
    scores: List[int]  # 待测策略坐 0..3 号位时各自的得分
    wins: int = 0  # 胡牌次数
    zimo: int = 0  # 其中自摸次数
    deal_ins: int = 0  # 点炮次数
    fan_total: int = 0  # 胡牌番数之和(封顶后)
    draws: int = 0  # 流局数


@dataclass
class EvalResult:
    candidate: str
    baseline: str
    deals: int
    seconds: float
    deal_means: List[float] = field(repr=False, default_factory=list)
    wins: int = 0
    zimo: int = 0
    deal_ins: int = 0
    fan_total: int = 0
    draws: int = 0

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
        var = sum((x - m) ** 2 for x in self.deal_means) / (n - 1)
        return math.sqrt(var / n)

    @property
    def ci95(self) -> Tuple[float, float]:
        half = 1.96 * self.stderr
        return (self.mean - half, self.mean + half)

    @property
    def stronger(self) -> bool:
        return self.ci95[0] > 0

    def summary(self) -> str:
        lo, hi = self.ci95
        g = self.games
        verdict = "显著更强" if self.stronger else ("显著更弱" if hi < 0 else "差距不显著")
        return "\n".join(
            [
                f"{self.candidate} 对 3 个 {self.baseline}: {self.deals} 副牌 × 4 个座位 = {g} 局,用时 {self.seconds:.1f} 秒",
                f"  平均每局得分 {self.mean:+.3f},95% 置信区间 [{lo:+.3f}, {hi:+.3f}] → {verdict}",
                f"  胡牌率 {self.wins / g:.1%}(自摸占 {self.zimo / max(self.wins, 1):.1%}),"
                f"点炮率 {self.deal_ins / g:.1%},平均胡牌番数 {self.fan_total / max(self.wins, 1):.2f},"
                f"流局率 {self.draws / g:.1%}",
            ]
        )


def play_deal(args: Tuple[str, str, int, Optional[dict]]) -> DealResult:
    """一副牌打 4 次。放在模块顶层是为了能被多进程调用。"""
    candidate, baseline, seed, config_dict = args
    config = RuleConfig.from_dict(config_dict) if config_dict else None
    result = DealResult(scores=[])
    dealer = seed % NUM_SEATS
    for seat in range(NUM_SEATS):
        agents = [make_agent(baseline, seed * 10 + s) for s in range(NUM_SEATS)]
        agents[seat] = make_agent(candidate, seed * 10 + seat)
        game = play_game(agents, seed=seed, config=config, dealer=dealer)
        result.scores.append(game.scores[seat])
        result.draws += game.end_reason == "wall_exhausted"
        for w in game.wins:
            if w.seat == seat:
                result.wins += 1
                result.zimo += w.zimo
                result.fan_total += w.capped_fan
            elif w.from_seat == seat:
                result.deal_ins += 1
    return result


def evaluate(
    candidate: str,
    baseline: str,
    num_deals: int,
    seed: int = 0,
    config: Optional[RuleConfig] = None,
    workers: int = 1,
) -> EvalResult:
    config_dict = config.to_dict() if config else None
    jobs = [(candidate, baseline, seed + i, config_dict) for i in range(num_deals)]
    start = time.perf_counter()
    if workers > 1:
        with Pool(workers) as pool:
            deals = pool.map(play_deal, jobs, chunksize=max(1, num_deals // (workers * 8)))
    else:
        deals = [play_deal(j) for j in jobs]
    out = EvalResult(candidate, baseline, num_deals, time.perf_counter() - start)
    for d in deals:
        out.deal_means.append(sum(d.scores) / NUM_SEATS)
        out.wins += d.wins
        out.zimo += d.zimo
        out.deal_ins += d.deal_ins
        out.fan_total += d.fan_total
        out.draws += d.draws
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ai.evaluate", description="同牌对比评估")
    names = "、".join(sorted(AGENTS))
    parser.add_argument("--candidate", default="rule", help=f"{names},或一个 .pt 模型文件")
    parser.add_argument("--baseline", default="simple", help="同上")
    parser.add_argument("-n", "--num-deals", type=int, default=500, help="多少副牌(每副打 4 局)")
    parser.add_argument("--seed", type=int, default=EVAL_SEED, help="第一副牌的种子;默认和训练数据的种子错开")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result = evaluate(args.candidate, args.baseline, args.num_deals, args.seed, workers=args.workers)
    print(result.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

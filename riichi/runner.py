"""把四个策略接到引擎上打完一场,以及批量对局统计。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .agents import Agent
from .config import RuleConfig
from .game import NUM_SEATS, Game


def play_game(
    agents: Sequence[Agent],
    seed: Optional[int] = None,
    config: Optional[RuleConfig] = None,
    record_events: bool = False,
) -> Game:
    if len(agents) != NUM_SEATS:
        raise ValueError("需要恰好 4 个策略")
    game = Game(config=config, seed=seed, record_events=record_events)
    while not game.is_over:
        s = game.current
        game.step(agents[s].act(game.observation(s), game.legal_actions()))
    return game


@dataclass
class Stats:
    games: int = 0
    hands: int = 0
    seconds: float = 0.0
    decisions: int = 0
    rank_counts: List[List[int]] = field(default_factory=lambda: [[0] * 4 for _ in range(NUM_SEATS)])
    total_points: List[float] = field(default_factory=lambda: [0.0] * NUM_SEATS)
    wins: int = 0
    ryukyoku: int = 0
    reasons: dict = field(default_factory=dict)

    def summary(self) -> str:
        g = max(self.games, 1)
        lines = [
            f"半庄 {self.games} 场,共 {self.hands} 局,用时 {self.seconds:.1f} 秒,"
            f"{self.games / max(self.seconds, 1e-9):.1f} 场/秒,{self.hands / max(self.seconds, 1e-9):.0f} 局/秒,"
            f"平均每场 {self.decisions / g:.0f} 次决策",
            f"和了 {self.wins} 次,流局 {self.ryukyoku} 次;流局原因 {self.reasons}",
        ]
        for s in range(NUM_SEATS):
            rc = self.rank_counts[s]
            avg_rank = sum((r + 1) * n for r, n in enumerate(rc)) / g
            lines.append(f"  座位 {s}: 平均顺位 {avg_rank:.2f},名次分 {self.total_points[s] / g:+.2f}/场,名次分布 {rc}")
        return "\n".join(lines)


def simulate(
    agents: Sequence[Agent], num_games: int, seed: int = 0, config: Optional[RuleConfig] = None
) -> Stats:
    """连打 num_games 场,第 i 场的种子是 seed + i。"""
    stats = Stats()
    start = time.perf_counter()
    for i in range(num_games):
        game = play_game(agents, seed=seed + i, config=config)
        stats.games += 1
        stats.hands += len(game.hand_results)
        stats.decisions += len(game.history)
        ranks = game.ranks()
        fp = game.final_points()
        for s in range(NUM_SEATS):
            stats.rank_counts[s][ranks[s]] += 1
            stats.total_points[s] += fp[s]
        for r in game.hand_results:
            if r["type"] == "win":
                stats.wins += len(r["wins"])
            else:
                stats.ryukyoku += 1
                stats.reasons[r["reason"]] = stats.reasons.get(r["reason"], 0) + 1
    stats.seconds = time.perf_counter() - start
    return stats

"""把四个策略接到引擎上打完一局,以及批量对局统计。"""
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
    dealer: int = 0,
    record_events: bool = False,
) -> Game:
    """用四个策略打完一局,返回结束后的 Game。"""
    if len(agents) != NUM_SEATS:
        raise ValueError("需要恰好 4 个策略")
    game = Game(config=config, seed=seed, dealer=dealer, record_events=record_events)
    while not game.is_over:
        seat = game.current
        game.step(agents[seat].act(game.observation(seat), game.legal_actions()))
    return game


@dataclass
class Stats:
    games: int = 0
    seconds: float = 0.0
    total_scores: List[int] = field(default_factory=lambda: [0] * NUM_SEATS)
    win_counts: List[int] = field(default_factory=lambda: [0] * NUM_SEATS)
    draws: int = 0  # 流局(牌墙摸完)的局数
    decisions: int = 0

    @property
    def games_per_second(self) -> float:
        return self.games / self.seconds if self.seconds else 0.0

    def summary(self) -> str:
        lines = [
            f"对局数 {self.games},用时 {self.seconds:.2f} 秒,"
            f"{self.games_per_second:.0f} 局/秒,平均每局 {self.decisions / max(self.games, 1):.0f} 次决策",
            f"流局(牌墙摸完) {self.draws} 局 ({self.draws / max(self.games, 1):.1%})",
        ]
        for s in range(NUM_SEATS):
            lines.append(
                f"  座位 {s}: 胡牌率 {self.win_counts[s] / max(self.games, 1):.1%},"
                f"平均得分 {self.total_scores[s] / max(self.games, 1):+.2f}"
            )
        return "\n".join(lines)


def simulate(
    agents: Sequence[Agent],
    num_games: int,
    seed: int = 0,
    config: Optional[RuleConfig] = None,
    rotate_dealer: bool = True,
) -> Stats:
    """连打 num_games 局。第 i 局的种子是 seed + i,庄家按局轮换。"""
    stats = Stats()
    start = time.perf_counter()
    for i in range(num_games):
        dealer = i % NUM_SEATS if rotate_dealer else 0
        game = play_game(agents, seed=seed + i, config=config, dealer=dealer)
        stats.games += 1
        stats.decisions += len(game.history)
        if game.end_reason == "wall_exhausted":
            stats.draws += 1
        for s in range(NUM_SEATS):
            stats.total_scores[s] += game.scores[s]
            stats.win_counts[s] += game.won[s]
    stats.seconds = time.perf_counter() - start
    return stats

"""日麻训练用的并行对局环境。结构照川麻的 ai/env.py。

BatchEnv      一个进程里并排开 n 场半庄。每一步把 n 个待决策的局面编码成一批交出去,收回 n 个动作。
ParallelEnv   开若干个进程,每个进程一个 BatchEnv,对外看起来还是一大批。

和川麻不同的地方:
- 一条轨迹是一个座位的一整场半庄(约 130 个有选择的决定),打完整场才交回。
- 回报: 每次决定之间点数的变化 / 1000;最后一步再加上名次马和返点差。
  一条轨迹的回报之和 = 终局名次分 − 第一次决定时的 (点数 − 起始点)/1000。
- 自己回合(刚摸完牌)的局面另带点炮标签(看全场算出来),继续训练点炮头。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from multiprocessing import get_context
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from riichi.actions import NUM_ACTIONS
from riichi.agents import Agent
from riichi.game import NUM_SEATS, Game, Phase

from . import make_agent
from .encoding import OBS_SHAPE, ORACLE_SHAPE, danger_labels, encode, encode_oracle

N = 34


@dataclass(frozen=True)
class SeatPlan:
    """每一场里谁由外部策略控制。含义同川麻的 ai.env.SeatPlan。"""

    learners: int = NUM_SEATS
    opponents: Tuple[str, ...] = ("shanten",)
    pool_size: int = 0
    pool_prob: float = 0.0

    def __post_init__(self) -> None:
        if not 1 <= self.learners <= NUM_SEATS:
            raise ValueError("learners 必须在 1..4")


@dataclass
class Episode:
    seed: int
    seat: int
    final_points: float  # 终局名次分
    rank: int  # 终局名次 0..3
    obs: np.ndarray  # (T, 80, 34) uint8
    mask: np.ndarray  # (T, 119) bool
    action: np.ndarray  # (T,) uint8
    reward: np.ndarray  # (T,) float32,名次分单位
    logp: np.ndarray  # (T,) float32
    value: np.ndarray  # (T,) float32
    danger: np.ndarray  # (T, 34) uint8
    has_danger: np.ndarray  # (T,) uint8
    oracle: Optional[np.ndarray] = None
    opponents: int = 0

    def __len__(self) -> int:
        return len(self.action)


@dataclass
class Batch:
    obs: np.ndarray
    mask: np.ndarray
    oracle: Optional[np.ndarray] = None
    policy: Optional[np.ndarray] = None


@dataclass
class EnvStats:
    games: int = 0
    decisions: int = 0
    forced: int = 0

    def add(self, other: "EnvStats") -> None:
        self.games += other.games
        self.decisions += other.decisions
        self.forced += other.forced


@dataclass
class _Track:
    obs: List[np.ndarray] = field(default_factory=list)
    mask: List[np.ndarray] = field(default_factory=list)
    oracle: List[np.ndarray] = field(default_factory=list)
    action: List[int] = field(default_factory=list)
    score: List[int] = field(default_factory=list)
    logp: List[float] = field(default_factory=list)
    value: List[float] = field(default_factory=list)
    danger: List[np.ndarray] = field(default_factory=list)
    has: List[int] = field(default_factory=list)


_NO_DANGER = np.zeros(N, dtype=np.uint8)


class BatchEnv:
    def __init__(
        self,
        num_games: int,
        seed: int = 0,
        plan: SeatPlan = SeatPlan(),
        oracle: bool = False,
        seed_step: int = 1,
    ) -> None:
        self.n = num_games
        self.plan = plan
        self.with_oracle = oracle
        self.stats = EnvStats()
        self._next_seed = seed
        self._seed_step = seed_step
        self._rng = random.Random(seed)
        self.obs = np.zeros((num_games, *OBS_SHAPE), dtype=np.uint8)
        self.mask = np.zeros((num_games, NUM_ACTIONS), dtype=np.bool_)
        self.oracle = np.zeros((num_games, *ORACLE_SHAPE), dtype=np.uint8) if oracle else None
        self.policy = np.zeros(num_games, dtype=np.int8)
        self.games: List[Game] = [None] * num_games  # type: ignore[list-item]
        self._seeds = [0] * num_games
        self._policies: List[List[int]] = [[] for _ in range(num_games)]
        self._opponents = [0] * num_games
        self._controllers: List[List[Optional[Agent]]] = [[] for _ in range(num_games)]
        self._tracks: List[List[Optional[_Track]]] = [[] for _ in range(num_games)]
        self._danger = [_NO_DANGER] * num_games
        self._has = [0] * num_games
        for i in range(num_games):
            self._new_game(i)
            self._advance(i, [])

    def observe(self) -> Batch:
        return Batch(self.obs, self.mask, self.oracle, self.policy)

    def step(
        self,
        actions: Sequence[int],
        logp: Optional[Sequence[float]] = None,
        value: Optional[Sequence[float]] = None,
    ) -> List[Episode]:
        done: List[Episode] = []
        for i in range(self.n):
            game = self.games[i]
            seat = game.current
            track = self._tracks[i][seat]
            if track is not None:
                track.obs.append(self.obs[i].copy())
                track.mask.append(self.mask[i].copy())
                if self.oracle is not None:
                    track.oracle.append(self.oracle[i].copy())
                track.action.append(int(actions[i]))
                track.score.append(game.scores[seat])
                track.logp.append(float(logp[i]) if logp is not None else 0.0)
                track.value.append(float(value[i]) if value is not None else 0.0)
                track.danger.append(self._danger[i])
                track.has.append(self._has[i])
            game.step(int(actions[i]))
            self.stats.decisions += 1
            self._advance(i, done)
        return done

    def _new_game(self, i: int) -> None:
        seed = self._next_seed
        self._next_seed += self._seed_step
        self._seeds[i] = seed
        self.games[i] = Game(seed=seed, record_events=False)
        plan = self.plan
        rng = self._rng
        if plan.pool_size and rng.random() < plan.pool_prob:
            learners = set(rng.sample(range(NUM_SEATS), rng.choice((1, 2))))
            self._controllers[i] = [None] * NUM_SEATS
            self._policies[i] = [0 if s in learners else rng.randint(1, plan.pool_size) for s in range(NUM_SEATS)]
        else:
            learners = set(rng.sample(range(NUM_SEATS), plan.learners))
            self._controllers[i] = [
                None if s in learners else make_agent(rng.choice(plan.opponents), seed * 10 + s)
                for s in range(NUM_SEATS)
            ]
            self._policies[i] = [0 if s in learners else -1 for s in range(NUM_SEATS)]
        self._opponents[i] = NUM_SEATS - len(learners)
        self._tracks[i] = [_Track() if s in learners else None for s in range(NUM_SEATS)]

    def _advance(self, i: int, done: List[Episode]) -> None:
        while True:
            game = self.games[i]
            controllers = self._controllers[i]
            while not game.is_over:
                legal = game.legal_actions()
                if len(legal) == 1:
                    game.step(legal[0])
                    self.stats.forced += 1
                    continue
                agent = controllers[game.current]
                if agent is None:
                    break
                game.step(agent.act(game.observation(game.current), legal))
            if not game.is_over:
                seat = game.current
                self.obs[i] = encode(game, seat)
                row = self.mask[i]
                row[:] = False
                row[game.legal_action_ids()] = True
                if self.oracle is not None:
                    self.oracle[i] = encode_oracle(game, seat)
                self.policy[i] = self._policies[i][seat]
                if self._tracks[i][seat] is not None and game.phase == Phase.TURN and game.drawn is not None:
                    self._danger[i] = danger_labels(game, seat)
                    self._has[i] = 1
                else:
                    self._danger[i] = _NO_DANGER
                    self._has[i] = 0
                return
            self._finish(i, done)
            self._new_game(i)

    def _finish(self, i: int, done: List[Episode]) -> None:
        game = self.games[i]
        self.stats.games += 1
        points = game.final_points()
        ranks = game.ranks()
        start = game.config.start_points
        for seat, track in enumerate(self._tracks[i]):
            if track is None or not track.action:
                continue
            final = game.scores[seat]
            scores = track.score + [final]
            reward = np.asarray(
                [(scores[k + 1] - scores[k]) / 1000 for k in range(len(track.action))], dtype=np.float32
            )
            reward[-1] += points[seat] - (final - start) / 1000  # 名次马和返点差
            done.append(
                Episode(
                    seed=self._seeds[i],
                    seat=seat,
                    final_points=points[seat],
                    rank=ranks[seat],
                    obs=np.stack(track.obs),
                    mask=np.stack(track.mask),
                    action=np.asarray(track.action, dtype=np.uint8),
                    reward=reward,
                    logp=np.asarray(track.logp, dtype=np.float32),
                    value=np.asarray(track.value, dtype=np.float32),
                    danger=np.stack(track.danger),
                    has_danger=np.asarray(track.has, dtype=np.uint8),
                    oracle=np.stack(track.oracle) if self.oracle is not None else None,
                    opponents=self._opponents[i],
                )
            )


def _worker(conn: Any, kwargs: dict) -> None:
    env = BatchEnv(**kwargs)
    conn.send((env.obs, env.mask, env.oracle, env.policy, [], env.stats))
    while True:
        msg = conn.recv()
        if msg is None:
            break
        actions, logp, value = msg
        episodes = env.step(actions, logp, value)
        conn.send((env.obs, env.mask, env.oracle, env.policy, episodes, env.stats))
    conn.close()


class ParallelEnv:
    def __init__(
        self,
        num_workers: int,
        games_per_worker: int,
        seed: int = 0,
        plan: SeatPlan = SeatPlan(),
        oracle: bool = False,
    ) -> None:
        self.num_workers = num_workers
        self.per = games_per_worker
        self.n = num_workers * games_per_worker
        self.obs = np.zeros((self.n, *OBS_SHAPE), dtype=np.uint8)
        self.mask = np.zeros((self.n, NUM_ACTIONS), dtype=np.bool_)
        self.oracle = np.zeros((self.n, *ORACLE_SHAPE), dtype=np.uint8) if oracle else None
        self.policy = np.zeros(self.n, dtype=np.int8)
        self._worker_stats = [EnvStats() for _ in range(num_workers)]
        ctx = get_context("spawn")
        self._conns = []
        self._procs = []
        for w in range(num_workers):
            parent, child = ctx.Pipe()
            kwargs = dict(num_games=games_per_worker, seed=seed + w, seed_step=num_workers, plan=plan, oracle=oracle)
            proc = ctx.Process(target=_worker, args=(child, kwargs), daemon=True)
            proc.start()
            child.close()
            self._conns.append(parent)
            self._procs.append(proc)
        for w in range(num_workers):
            self._receive(w)

    @property
    def stats(self) -> EnvStats:
        total = EnvStats()
        for s in self._worker_stats:
            total.add(s)
        return total

    def observe(self) -> Batch:
        return Batch(self.obs, self.mask, self.oracle, self.policy)

    def step(self, actions, logp=None, value=None) -> List[Episode]:
        actions = np.asarray(actions)
        logp = None if logp is None else np.asarray(logp, dtype=np.float32)
        value = None if value is None else np.asarray(value, dtype=np.float32)
        for w, conn in enumerate(self._conns):
            sl = slice(w * self.per, (w + 1) * self.per)
            conn.send((actions[sl], None if logp is None else logp[sl], None if value is None else value[sl]))
        episodes: List[Episode] = []
        for w in range(self.num_workers):
            episodes.extend(self._receive(w))
        return episodes

    def _receive(self, w: int) -> List[Episode]:
        obs, mask, oracle, policy, episodes, stats = self._conns[w].recv()
        sl = slice(w * self.per, (w + 1) * self.per)
        self.obs[sl] = obs
        self.mask[sl] = mask
        self.policy[sl] = policy
        if self.oracle is not None:
            self.oracle[sl] = oracle
        self._worker_stats[w] = stats
        return episodes

    def close(self) -> None:
        for conn in self._conns:
            try:
                conn.send(None)
                conn.close()
            except (BrokenPipeError, OSError):
                pass
        for proc in self._procs:
            proc.join(timeout=5)
            if proc.is_alive():
                proc.terminate()
        self._conns, self._procs = [], []

    def __enter__(self) -> "ParallelEnv":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

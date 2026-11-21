"""训练用的并行对局环境(阶段 4b)。

BatchEnv      一个进程里并排开 n 局。每一步把 n 个待决策的局面编码成一批交出去,
              收回 n 个动作,各推进一步;打完的局自动换新的一局。
ParallelEnv   开若干个进程,每个进程里一个 BatchEnv,对外看起来还是一大批。

"待决策"只指由外部策略(要训练的网络)控制的座位。其余座位由进程里的固定策略
(规则型 AI 等)直接走完,不会出现在批里。只有一个合法动作的局面也自动走掉。

用法:

    env = ParallelEnv(num_workers=12, games_per_worker=64, plan=SeatPlan(learners=4))
    while 训练中:
        batch = env.observe()                 # obs (B, C, 27) uint8, mask (B, 115) bool
        actions, logp, value = 网络(batch)
        episodes = env.step(actions, logp, value)   # 这一步里打完的局,按座位切成一条条轨迹
    env.close()
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from multiprocessing import get_context
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from chuanma.actions import NUM_ACTIONS
from chuanma.agents import Agent
from chuanma.config import RuleConfig
from chuanma.game import NUM_SEATS, Game

from . import make_agent
from .encoding import OBS_SHAPE, ORACLE_SHAPE, encode, encode_oracle


@dataclass(frozen=True)
class SeatPlan:
    """每一局里谁由外部策略控制。

    learners: 几个座位交给外部策略(1..4),每局随机挑座位。
    opponents: 其余座位用哪些固定策略(ai.AGENTS 里的名字),每个座位随机挑一个。
    """

    learners: int = NUM_SEATS
    opponents: Tuple[str, ...] = ("rule",)

    def __post_init__(self) -> None:
        if not 1 <= self.learners <= NUM_SEATS:
            raise ValueError("learners 必须在 1..4")
        if self.learners < NUM_SEATS and not self.opponents:
            raise ValueError("有固定策略的座位时 opponents 不能为空")


@dataclass
class Episode:
    """一局里一个座位的全部决策。长度 T = 这个座位做了几次(非强制的)决定。"""

    seed: int
    seat: int
    final_score: int
    obs: np.ndarray  # (T, C, 27) uint8
    mask: np.ndarray  # (T, 115) bool
    action: np.ndarray  # (T,) uint8
    reward: np.ndarray  # (T,) float32: 做完这个决定到下一次决定(或终局)之间得分的变化
    logp: np.ndarray  # (T,) float32: 外部策略给的,原样带回
    value: np.ndarray  # (T,) float32: 同上
    oracle: Optional[np.ndarray] = None  # (T, 16, 27) uint8,开了 oracle 才有

    def __len__(self) -> int:
        return len(self.action)


@dataclass
class Batch:
    obs: np.ndarray  # (B, C, 27) uint8
    mask: np.ndarray  # (B, 115) bool
    oracle: Optional[np.ndarray] = None  # (B, 16, 27) uint8


@dataclass
class EnvStats:
    games: int = 0  # 打完的局数
    decisions: int = 0  # 外部策略做的决定数
    forced: int = 0  # 只有一个合法动作、自动走掉的次数

    def add(self, other: "EnvStats") -> None:
        self.games += other.games
        self.decisions += other.decisions
        self.forced += other.forced


@dataclass
class _Track:
    """一个座位在当前这局里攒下的轨迹。"""

    obs: List[np.ndarray] = field(default_factory=list)
    mask: List[np.ndarray] = field(default_factory=list)
    oracle: List[np.ndarray] = field(default_factory=list)
    action: List[int] = field(default_factory=list)
    score: List[int] = field(default_factory=list)
    logp: List[float] = field(default_factory=list)
    value: List[float] = field(default_factory=list)


class BatchEnv:
    def __init__(
        self,
        num_games: int,
        seed: int = 0,
        plan: SeatPlan = SeatPlan(),
        config: Optional[RuleConfig] = None,
        oracle: bool = False,
        seed_step: int = 1,
    ) -> None:
        """seed: 第一局的种子;之后每开一局加 seed_step。多进程时各进程错开起点、共用步长,种子不重复。"""
        self.n = num_games
        self.plan = plan
        self.config = config
        self.with_oracle = oracle
        self.stats = EnvStats()
        self._next_seed = seed
        self._seed_step = seed_step
        self._rng = random.Random(seed)

        self.obs = np.zeros((num_games, *OBS_SHAPE), dtype=np.uint8)
        self.mask = np.zeros((num_games, NUM_ACTIONS), dtype=np.bool_)
        self.oracle = np.zeros((num_games, *ORACLE_SHAPE), dtype=np.uint8) if oracle else None

        self.games: List[Game] = [None] * num_games  # type: ignore[list-item]
        self._seeds = [0] * num_games
        self._controllers: List[List[Optional[Agent]]] = [[] for _ in range(num_games)]
        self._tracks: List[List[Optional[_Track]]] = [[] for _ in range(num_games)]
        for i in range(num_games):
            self._new_game(i)
            self._advance(i, [])

    # ------------------------------------------------------------------ 对外

    def observe(self) -> Batch:
        """每个位置上当前待决策的局面。数组是环境内部的缓冲区,下一次 step 会改写它。"""
        return Batch(self.obs, self.mask, self.oracle)

    def step(
        self,
        actions: Sequence[int],
        logp: Optional[Sequence[float]] = None,
        value: Optional[Sequence[float]] = None,
    ) -> List[Episode]:
        """每个位置执行一个动作。返回这一步里打完的那些局的轨迹。"""
        done: List[Episode] = []
        for i in range(self.n):
            game = self.games[i]
            seat = game.current
            track = self._tracks[i][seat]
            track.obs.append(self.obs[i].copy())
            track.mask.append(self.mask[i].copy())
            if self.oracle is not None:
                track.oracle.append(self.oracle[i].copy())
            track.action.append(int(actions[i]))
            track.score.append(game.scores[seat])
            track.logp.append(float(logp[i]) if logp is not None else 0.0)
            track.value.append(float(value[i]) if value is not None else 0.0)
            game.step(int(actions[i]))
            self.stats.decisions += 1
            self._advance(i, done)
        return done

    # ------------------------------------------------------------------ 内部

    def _new_game(self, i: int) -> None:
        seed = self._next_seed
        self._next_seed += self._seed_step
        self._seeds[i] = seed
        self.games[i] = Game(config=self.config, seed=seed, dealer=seed % NUM_SEATS, record_events=False)
        learners = set(self._rng.sample(range(NUM_SEATS), self.plan.learners))
        self._controllers[i] = [
            None if s in learners else make_agent(self._rng.choice(self.plan.opponents), seed * 10 + s)
            for s in range(NUM_SEATS)
        ]
        self._tracks[i] = [_Track() if s in learners else None for s in range(NUM_SEATS)]

    def _advance(self, i: int, done: List[Episode]) -> None:
        """推进第 i 个位置,直到轮到外部策略做一个真正有选择的决定。打完就收尾并开新局。"""
        while True:
            game = self.games[i]
            controllers = self._controllers[i]
            while not game.is_over:
                legal = game._legal
                if len(legal) == 1:
                    game.step(legal[0])
                    self.stats.forced += 1
                    continue
                agent = controllers[game.current]
                if agent is None:
                    break
                game.step(agent.act(game.observation(game.current), list(legal)))
            if not game.is_over:
                seat = game.current
                self.obs[i] = encode(game, seat)
                row = self.mask[i]
                row[:] = False
                row[game.legal_action_ids()] = True
                if self.oracle is not None:
                    self.oracle[i] = encode_oracle(game, seat)
                return
            self._finish(i, done)
            self._new_game(i)

    def _finish(self, i: int, done: List[Episode]) -> None:
        game = self.games[i]
        self.stats.games += 1
        for seat, track in enumerate(self._tracks[i]):
            if track is None or not track.action:
                continue
            final = game.scores[seat]
            scores = track.score + [final]
            reward = np.asarray([scores[k + 1] - scores[k] for k in range(len(track.action))], dtype=np.float32)
            done.append(
                Episode(
                    seed=self._seeds[i],
                    seat=seat,
                    final_score=final,
                    obs=np.stack(track.obs),
                    mask=np.stack(track.mask),
                    action=np.asarray(track.action, dtype=np.uint8),
                    reward=reward,
                    logp=np.asarray(track.logp, dtype=np.float32),
                    value=np.asarray(track.value, dtype=np.float32),
                    oracle=np.stack(track.oracle) if self.oracle is not None else None,
                )
            )


# ---------------------------------------------------------------------- 多进程


def _worker(conn: Any, kwargs: dict) -> None:
    env = BatchEnv(**kwargs)
    conn.send((env.obs, env.mask, env.oracle, [], env.stats))
    while True:
        msg = conn.recv()
        if msg is None:
            break
        actions, logp, value = msg
        episodes = env.step(actions, logp, value)
        conn.send((env.obs, env.mask, env.oracle, episodes, env.stats))
    conn.close()


class ParallelEnv:
    """num_workers 个进程,每个进程 games_per_worker 局。批的大小是两者的乘积。"""

    def __init__(
        self,
        num_workers: int,
        games_per_worker: int,
        seed: int = 0,
        plan: SeatPlan = SeatPlan(),
        config: Optional[RuleConfig] = None,
        oracle: bool = False,
    ) -> None:
        self.num_workers = num_workers
        self.per = games_per_worker
        self.n = num_workers * games_per_worker
        self.with_oracle = oracle
        self.obs = np.zeros((self.n, *OBS_SHAPE), dtype=np.uint8)
        self.mask = np.zeros((self.n, NUM_ACTIONS), dtype=np.bool_)
        self.oracle = np.zeros((self.n, *ORACLE_SHAPE), dtype=np.uint8) if oracle else None
        self._worker_stats = [EnvStats() for _ in range(num_workers)]

        ctx = get_context("spawn")
        self._conns = []
        self._procs = []
        for w in range(num_workers):
            parent, child = ctx.Pipe()
            kwargs = dict(
                num_games=games_per_worker,
                seed=seed + w,
                seed_step=num_workers,
                plan=plan,
                config=config,
                oracle=oracle,
            )
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
        return Batch(self.obs, self.mask, self.oracle)

    def step(
        self,
        actions: Sequence[int],
        logp: Optional[Sequence[float]] = None,
        value: Optional[Sequence[float]] = None,
    ) -> List[Episode]:
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
        obs, mask, oracle, episodes, stats = self._conns[w].recv()
        sl = slice(w * self.per, (w + 1) * self.per)
        self.obs[sl] = obs
        self.mask[sl] = mask
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

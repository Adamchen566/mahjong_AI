"""测训练环境的速度。

    python -m ai.bench --workers 12

测四样东西:
    1. 编码一个局面要多久(直接读 Game / 经过 observation 字典)
    2. 单进程 BatchEnv,随机策略
    3. 多进程 ParallelEnv,随机策略(不含网络推理,量的是对局 + 编码 + 进程通信的上限)
    4. 多进程 ParallelEnv,1 个外部座位 + 3 个规则型 AI
    5. 给了 --model 时: 四个座位都由网络在显卡上推理的自我对弈(模型文件,或 new 表示一个没训练过的网络)

随机策略打的局比正常的局长(没人会胡),所以"局/秒"偏低,"决定/秒"更有参考价值。
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional

import numpy as np

from chuanma.game import Game

from .encoding import encode, encode_obs, encode_oracle
from .env import BatchEnv, ParallelEnv, SeatPlan


def random_actions(mask: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """每一行从合法动作里均匀随机挑一个。"""
    noise = rng.random(mask.shape, dtype=np.float32)
    noise[~mask] = -1.0
    return noise.argmax(axis=1)


def bench_encode(num_games: int = 200) -> dict:
    rng = np.random.default_rng(0)
    states = 0
    t_direct = t_obs = t_oracle = 0.0
    for seed in range(num_games):
        game = Game(seed=seed, record_events=False)
        while not game.is_over:
            seat = game.current
            t0 = time.perf_counter()
            encode(game, seat)
            t1 = time.perf_counter()
            encode_obs(game.observation(seat))
            t2 = time.perf_counter()
            encode_oracle(game, seat)
            t3 = time.perf_counter()
            t_direct += t1 - t0
            t_obs += t2 - t1
            t_oracle += t3 - t2
            states += 1
            ids = game.legal_action_ids()
            game.step(ids[int(rng.integers(len(ids)))])
    return {
        "states": states,
        "direct_us": t_direct / states * 1e6,
        "via_obs_us": t_obs / states * 1e6,
        "oracle_us": t_oracle / states * 1e6,
    }


def bench_env(env, seconds: float) -> dict:
    rng = np.random.default_rng(0)
    before = env.stats
    games0, dec0 = before.games, before.decisions
    samples = 0
    ticks = 0
    start = time.perf_counter()
    while time.perf_counter() - start < seconds:
        batch = env.observe()
        samples += sum(len(e) for e in env.step(random_actions(batch.mask, rng)))
        ticks += 1
    elapsed = time.perf_counter() - start
    after = env.stats
    return {
        "batch": env.n,
        "ticks_per_s": ticks / elapsed,
        "decisions_per_s": (after.decisions - dec0) / elapsed,
        "games_per_s": (after.games - games0) / elapsed,
    }


def bench_selfplay(model_path: str, workers: int, per: int, seconds: float) -> dict:
    import torch

    from .model import MahjongNet, load_model
    from .selfplay import policy_step

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = MahjongNet().to(device).eval() if model_path == "new" else load_model(model_path, device)
    with ParallelEnv(workers, per, oracle=True) as env:
        for _ in range(20):  # 预热
            env.step(policy_step(model, env.observe(), device)[0])
        before = env.stats
        infer = 0.0
        ticks = 0
        start = time.perf_counter()
        while time.perf_counter() - start < seconds:
            t0 = time.perf_counter()
            actions, logp, value = policy_step(model, env.observe(), device)
            infer += time.perf_counter() - t0
            env.step(actions, logp, value)
            ticks += 1
        elapsed = time.perf_counter() - start
        after = env.stats
        return {
            "batch": env.n,
            "ticks_per_s": ticks / elapsed,
            "decisions_per_s": (after.decisions - before.decisions) / elapsed,
            "games_per_s": (after.games - before.games) / elapsed,
            "infer_share": infer / elapsed,
            "device": str(device),
        }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ai.bench", description="训练环境测速")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--games-per-worker", type=int, default=64)
    parser.add_argument("--seconds", type=float, default=10.0, help="每一项测多久")
    parser.add_argument("--model", default=None, help="模型文件或 new: 加测带网络推理的自我对弈")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    e = bench_encode()
    print(f"编码({e['states']} 个局面)")
    print(f"  直接读 Game        {e['direct_us']:.1f} 微秒/次")
    print(f"  经 observation 字典 {e['via_obs_us']:.1f} 微秒/次")
    print(f"  价值头的额外输入    {e['oracle_us']:.1f} 微秒/次")

    def show(title: str, r: dict) -> None:
        print(f"{title}(每批 {r['batch']} 个局面)")
        print(
            f"  {r['decisions_per_s']:,.0f} 个决定/秒,{r['games_per_s']:,.0f} 局/秒,"
            f"{r['ticks_per_s']:.0f} 批/秒"
        )

    show("单进程,4 个座位都是随机策略", bench_env(BatchEnv(args.games_per_worker), args.seconds))
    with ParallelEnv(args.workers, args.games_per_worker) as env:
        show(f"{args.workers} 进程,4 个座位都是随机策略", bench_env(env, args.seconds))
    plan = SeatPlan(learners=1, opponents=("rule",))
    with ParallelEnv(args.workers, args.games_per_worker, plan=plan) as env:
        show(f"{args.workers} 进程,1 个随机策略 + 3 个规则型 AI", bench_env(env, args.seconds))
    if args.model:
        r = bench_selfplay(args.model, args.workers, args.games_per_worker, args.seconds)
        show(f"{args.workers} 进程,4 个座位都由网络推理({r['device']})", r)
        print(f"  其中推理占 {r['infer_share']:.0%} 的时间")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

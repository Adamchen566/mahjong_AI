"""自我对弈强化学习(阶段 4d)。

    python -m ai.train_ppo --init checkpoints/bc/best.pt --out checkpoints/ppo --minutes 60
    python -m ai.train_ppo --out checkpoints/ppo --resume --minutes 240      # 接着上次的训

每一轮:
    1. 采样  12 个进程并排打牌,显卡统一推理,攒够一定数量的决定
    2. 更新  PPO
    3. 记录  写一行日志,存 latest.pt(随时可以中断,下次 --resume 接上)
每隔几轮把当前模型放进对手池;每隔几轮和规则型 AI 打一次同牌对比,成绩创新高就另存 best.pt。

对手池: 1 号位永远是起点模型(模仿模型),其余位置轮流换成训练途中的旧版本。
一半的局是四个座位都是当前模型,另一半是当前模型坐 1 到 2 个座位、其余从池里抽。
"""
from __future__ import annotations

import argparse
import copy
import csv
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

from .env import Batch, Episode, ParallelEnv, SeatPlan
from .evaluate import EVAL_SEED, evaluate
from .model import MahjongNet, ModelConfig, load_checkpoint, save_checkpoint
from .ppo import build_rollout, ppo_update

TRAIN_SEED = 100_000_000  # 自我对弈用的牌从这里起,和模仿数据、评估的种子都不重叠


@torch.no_grad()
def act(
    learner: MahjongNet, pool: List[MahjongNet], batch: Batch, device: torch.device
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """给一批局面选动作。局面按策略编号分给当前模型或对手池里的模型。"""
    obs = torch.from_numpy(batch.obs).to(device)
    mask = torch.from_numpy(batch.mask).to(device)
    oracle = torch.from_numpy(batch.oracle).to(device)
    policy = torch.from_numpy(batch.policy).to(device)
    n = len(policy)
    action = torch.zeros(n, dtype=torch.long, device=device)
    logp = torch.zeros(n, device=device)
    value = torch.zeros(n, device=device)
    for pid in policy.unique().tolist():
        idx = (policy == pid).nonzero(as_tuple=True)[0]
        with torch.autocast(device.type, enabled=device.type == "cuda"):
            if pid == 0:
                out = learner(obs[idx], mask[idx], oracle[idx])
            else:
                out = pool[pid - 1](obs[idx], mask[idx])
        dist = torch.distributions.Categorical(logits=out.logits)
        a = dist.sample()
        action[idx] = a
        if pid == 0:
            logp[idx] = dist.log_prob(a)
            value[idx] = out.oracle_value
    return action.cpu().numpy(), logp.cpu().numpy(), value.cpu().numpy()


def collect(env: ParallelEnv, learner: MahjongNet, pool: List[MahjongNet], device: torch.device, decisions: int) -> List[Episode]:
    episodes: List[Episode] = []
    got = 0
    while got < decisions:
        done = env.step(*act(learner, pool, env.observe(), device))
        episodes.extend(done)
        got += sum(len(e) for e in done)
    return episodes


def train(
    out_dir: str,
    init: Optional[str] = None,
    resume: bool = False,
    iterations: int = 1_000_000,
    minutes: Optional[float] = None,
    rollout_decisions: int = 300_000,
    workers: int = 12,
    games_per_worker: int = 64,
    lr: float = 1e-4,
    epochs: int = 2,
    batch_size: int = 4096,
    clip: float = 0.2,
    ent_coef: float = 0.01,
    vf_coef: float = 0.5,
    lam: float = 0.95,
    pool_size: int = 4,
    pool_prob: float = 0.5,
    snapshot_every: int = 10,
    eval_every: int = 20,
    eval_deals: int = 1000,
    eval_workers: int = 12,
    device: Optional[str] = None,
    log=print,
) -> Dict[str, float]:
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    latest = out / "latest.pt"

    state = {"iteration": 0, "games": 0, "decisions": 0, "seconds": 0.0, "best_eval": float("-inf"), "snapshots": 0}
    if resume:
        payload = load_checkpoint(latest, dev)
    elif init:
        payload = load_checkpoint(init, dev)
    else:
        raise ValueError("要么给 init(起点模型),要么 resume")
    config = ModelConfig(**payload["config"])
    learner = MahjongNet(config).to(dev)
    learner.load_state_dict(payload["model"])
    learner.eval()
    opt = torch.optim.Adam(learner.parameters(), lr=lr)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")

    pool = [copy.deepcopy(learner).eval() for _ in range(pool_size)]
    if resume:
        state.update(payload["state"])
        opt.load_state_dict(payload["optimizer"])
        for g in opt.param_groups:
            g["lr"] = lr
        for net, weights in zip(pool, payload["pool"]):
            net.load_state_dict(weights)
        log(f"接着第 {state['iteration']} 轮继续,已打 {state['games']:,} 局")
    else:
        log(f"从 {init} 开始")

    plan = SeatPlan(learners=4, pool_size=pool_size, pool_prob=pool_prob if pool_size else 0.0)
    env = ParallelEnv(workers, games_per_worker, seed=TRAIN_SEED + state["games"] * 2, plan=plan, oracle=True)

    log_path = out / "log.csv"
    fresh = not (resume and log_path.exists())
    log_file = log_path.open("w" if fresh else "a", newline="", encoding="utf-8")
    writer: Optional[csv.DictWriter] = None

    def save(path: Path) -> None:
        save_checkpoint(
            path,
            learner,
            optimizer=opt.state_dict(),
            pool=[net.state_dict() for net in pool],
            state=dict(state),
            stage="ppo",
        )

    session_start = time.perf_counter()
    last_eval: Dict[str, float] = {}
    row: Dict[str, float] = {}
    try:
        for _ in range(iterations):
            if minutes is not None and (time.perf_counter() - session_start) / 60 >= minutes:
                break
            t0 = time.perf_counter()
            games_before = env.stats.games
            episodes = collect(env, learner, pool, dev, rollout_decisions)
            t1 = time.perf_counter()
            data = build_rollout(episodes, dev, lam)
            metrics = ppo_update(learner, opt, scaler, data, epochs, batch_size, clip, vf_coef, ent_coef)
            t2 = time.perf_counter()

            state["iteration"] += 1
            state["games"] += env.stats.games - games_before
            state["decisions"] += len(data)
            state["seconds"] += t2 - t0
            it = state["iteration"]

            mixed = [e.final_score for e in episodes if e.opponents]
            row = {
                "iteration": it,
                "games": state["games"],
                "decisions": state["decisions"],
                "hours": round(state["seconds"] / 3600, 3),
                "sample_seconds": round(t1 - t0, 1),
                "update_seconds": round(t2 - t1, 1),
                "vs_pool_score": round(float(np.mean(mixed)), 4) if mixed else 0.0,
                "episode_length": round(len(data) / len(episodes), 2),
                **{k: round(v, 5) for k, v in metrics.items()},
                "eval_score": "",
                "eval_lo": "",
                "eval_hi": "",
                "eval_win_rate": "",
                "eval_deal_in_rate": "",
            }

            if snapshot_every and pool_size > 1 and it % snapshot_every == 0:
                slot = 1 + state["snapshots"] % (pool_size - 1)  # 0 号位留给起点模型
                pool[slot].load_state_dict(learner.state_dict())
                state["snapshots"] += 1

            save(latest)
            if eval_every and it % eval_every == 0:
                result = evaluate(str(latest), "rule", eval_deals, seed=EVAL_SEED, workers=eval_workers)
                lo, hi = result.ci95
                last_eval = {"score": result.mean, "lo": lo, "hi": hi}
                row.update(
                    eval_score=round(result.mean, 4),
                    eval_lo=round(lo, 4),
                    eval_hi=round(hi, 4),
                    eval_win_rate=round(result.wins / result.games, 4),
                    eval_deal_in_rate=round(result.deal_ins / result.games, 4),
                )
                if result.mean > state["best_eval"]:
                    state["best_eval"] = result.mean
                    save(latest)
                    save(out / "best.pt")
                log(
                    f"  评估: 对 3 个规则型 AI {result.games} 局,平均每局 {result.mean:+.3f} [{lo:+.3f}, {hi:+.3f}],"
                    f"胡牌率 {result.wins / result.games:.1%},点炮率 {result.deal_ins / result.games:.1%}"
                )

            if writer is None:
                writer = csv.DictWriter(log_file, fieldnames=list(row))
                if fresh:
                    writer.writeheader()
            writer.writerow(row)
            log_file.flush()
            log(
                f"第 {it} 轮: 累计 {state['games']:,} 局 / {state['seconds'] / 3600:.2f} 小时,"
                f"采样 {t1 - t0:.0f} 秒 + 更新 {t2 - t1:.0f} 秒,对池得分 {row['vs_pool_score']:+.3f},"
                f"熵 {metrics['entropy']:.3f},KL {metrics['kl']:.4f},"
                f"价值解释度 {metrics['ev_value']:.2f} / 看全场 {metrics['ev_oracle']:.2f}"
            )
    except KeyboardInterrupt:
        log("收到中断,已保存的 latest.pt 可以用 --resume 接着训")
    finally:
        env.close()
        log_file.close()
    return {**{k: v for k, v in row.items() if isinstance(v, (int, float))}, **{f"eval_{k}": v for k, v in last_eval.items()}}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ai.train_ppo", description="自我对弈强化学习")
    parser.add_argument("--out", default="checkpoints/ppo")
    parser.add_argument("--init", default=None, help="起点模型,一般是模仿模型")
    parser.add_argument("--resume", action="store_true", help="从 out 目录里的 latest.pt 接着训")
    parser.add_argument("--iterations", type=int, default=1_000_000)
    parser.add_argument("--minutes", type=float, default=None, help="训到这么多分钟就停(这一轮做完才停)")
    parser.add_argument("--rollout", type=int, default=300_000, help="每轮采样多少个决定")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--games-per-worker", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--clip", type=float, default=0.2)
    parser.add_argument("--ent-coef", type=float, default=0.01)
    parser.add_argument("--lam", type=float, default=0.95)
    parser.add_argument("--pool-size", type=int, default=4)
    parser.add_argument("--pool-prob", type=float, default=0.5)
    parser.add_argument("--snapshot-every", type=int, default=10)
    parser.add_argument("--eval-every", type=int, default=20)
    parser.add_argument("--eval-deals", type=int, default=1000)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    train(
        args.out,
        init=args.init,
        resume=args.resume,
        iterations=args.iterations,
        minutes=args.minutes,
        rollout_decisions=args.rollout,
        workers=args.workers,
        games_per_worker=args.games_per_worker,
        lr=args.lr,
        epochs=args.epochs,
        batch_size=args.batch_size,
        clip=args.clip,
        ent_coef=args.ent_coef,
        lam=args.lam,
        pool_size=args.pool_size,
        pool_prob=args.pool_prob,
        snapshot_every=args.snapshot_every,
        eval_every=args.eval_every,
        eval_deals=args.eval_deals,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

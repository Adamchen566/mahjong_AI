"""生成模仿学习的数据: 让固定策略(默认规则型)互打整场半庄,记下每个决策点。

    python -m riichi_ai.generate --games 6000 --workers 12 --out data/rbc/clean
    python -m riichi_ai.generate --games 2000 --workers 12 --explore 0.1 --seed 100000 --out data/rbc/explore

每个分片是一个 .npz 文件(n = 决策点数):

    obs      (n, 80, 34) uint8   局面编码,见 riichi_ai/encoding.py
    oracle   (n, 17, 34) uint8   别人的手牌、牌墙、里宝,只给价值头用
    mask     (n, 15)     uint8   119 个动作的合法掩码,按位压缩
    action   (n,)        uint8   老师选的动作
    ret      (n,)        float32 从这个决策点到终局,这个座位还会得多少名次分
    danger   (n, 5)      uint8   34 种牌打出去会不会被荣和,按位压缩(只在自己回合有意义)
    has_danger (n,)      uint8   这一条有没有点炮标签(自己回合、刚摸完牌)
    seed, seat

回报的约定(和自我对弈一致): 每次决定之间点数的变化 / 1000,终局再加上名次马和返点差,
加起来正好等于终局的名次分减去决定当时的 (点数 − 起始点)/1000。只有一个合法动作的局面不记。
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from riichi.actions import NUM_ACTIONS
from riichi.game import NUM_SEATS, Game, Phase

from . import AGENTS, make_agent
from .encoding import NUM_CHANNELS, ORACLE_CHANNELS, danger_labels, encode, encode_oracle

FORMAT_VERSION = 1
MASK_BYTES = (NUM_ACTIONS + 7) // 8


def remaining_value(game: Game, seat: int, score_then: int) -> float:
    """终局名次分 − 决定当时的 (点数 − 起始点)/1000。"""
    return game.final_points()[seat] - (score_then - game.config.start_points) / 1000


def play_and_record(seed: int, teacher: str, explore: float, out: dict) -> None:
    game = Game(seed=seed, record_events=False)
    agents = [make_agent(teacher, seed * 10 + s) for s in range(NUM_SEATS)]
    rng = random.Random(seed ^ 0x5EED)
    start = len(out["action"])
    then: List[Tuple[int, int]] = []
    while not game.is_over:
        seat = game.current
        legal = game.legal_actions()
        if len(legal) == 1:
            game.step(legal[0])
            continue
        choice = agents[seat].act(game.observation(seat), legal)
        out["obs"].append(encode(game, seat))
        out["oracle"].append(encode_oracle(game, seat))
        mask = np.zeros(NUM_ACTIONS, dtype=np.bool_)
        mask[[a.id for a in legal]] = True
        out["mask"].append(mask)
        out["action"].append(choice.id)
        has = game.phase == Phase.TURN and game.drawn is not None
        out["danger"].append(danger_labels(game, seat) if has else np.zeros(34, np.uint8))
        out["has_danger"].append(1 if has else 0)
        out["seed"].append(seed)
        out["seat"].append(seat)
        then.append((seat, game.scores[seat]))
        if explore and rng.random() < explore:
            choice = rng.choice(legal)
        game.step(choice)
    for seat, score in then:
        out["ret"].append(remaining_value(game, seat, score))
    assert len(out["ret"]) == len(out["action"]) and len(out["action"]) - start == len(then)


def _write_shard(job: Tuple[str, int, int, str, float]) -> Tuple[int, int]:
    path, first_seed, num_games, teacher, explore = job
    keys = ("obs", "oracle", "mask", "action", "ret", "danger", "has_danger", "seed", "seat")
    out: dict = {k: [] for k in keys}
    for i in range(num_games):
        play_and_record(first_seed + i, teacher, explore, out)
    n = len(out["action"])
    np.savez_compressed(
        path,
        obs=np.stack(out["obs"]) if n else np.zeros((0, NUM_CHANNELS, 34), np.uint8),
        oracle=np.stack(out["oracle"]) if n else np.zeros((0, ORACLE_CHANNELS, 34), np.uint8),
        mask=np.packbits(np.stack(out["mask"]), axis=1) if n else np.zeros((0, MASK_BYTES), np.uint8),
        action=np.asarray(out["action"], dtype=np.uint8),
        ret=np.asarray(out["ret"], dtype=np.float32),
        danger=np.packbits(np.stack(out["danger"]), axis=1) if n else np.zeros((0, 5), np.uint8),
        has_danger=np.asarray(out["has_danger"], dtype=np.uint8),
        seed=np.asarray(out["seed"], dtype=np.int64),
        seat=np.asarray(out["seat"], dtype=np.uint8),
    )
    return num_games, n


def generate(
    out_dir: str,
    num_games: int,
    teacher: str = "shanten",
    seed: int = 0,
    workers: int = 1,
    shard_games: int = 50,
    explore: float = 0.0,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for k, first in enumerate(range(0, num_games, shard_games)):
        count = min(shard_games, num_games - first)
        jobs.append((str(out / f"shard_{k:05d}.npz"), seed + first, count, teacher, explore))
    start = time.perf_counter()
    if workers > 1:
        with Pool(workers) as pool:
            results = pool.map(_write_shard, jobs, chunksize=1)
    else:
        results = [_write_shard(j) for j in jobs]
    seconds = time.perf_counter() - start
    samples = sum(n for _, n in results)
    meta = {
        "format_version": FORMAT_VERSION,
        "teacher": teacher,
        "games": num_games,
        "samples": samples,
        "shards": len(jobs),
        "seed": seed,
        "explore": explore,
        "obs_channels": NUM_CHANNELS,
        "oracle_channels": ORACLE_CHANNELS,
        "seconds": round(seconds, 1),
        "games_per_second": round(num_games / seconds, 2) if seconds else None,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m riichi_ai.generate", description="生成日麻模仿学习数据")
    parser.add_argument("--out", required=True)
    parser.add_argument("--games", type=int, default=1000, help="多少场半庄")
    parser.add_argument("--teacher", choices=sorted(AGENTS), default="shanten")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--shard-games", type=int, default=50)
    parser.add_argument("--explore", type=float, default=0.0)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    meta = generate(args.out, args.games, args.teacher, args.seed, args.workers, args.shard_games, args.explore)
    print(
        f"{meta['games']} 场半庄,{meta['samples']} 个决策点,{meta['shards']} 个分片,"
        f"用时 {meta['seconds']} 秒({meta['games_per_second']} 场/秒)→ {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

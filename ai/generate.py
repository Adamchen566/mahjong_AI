"""生成模仿学习的数据: 让固定策略互打,记下每个决策点的(局面编码,老师的动作)。

    python -m ai.generate --games 50000 --workers 12 --out data/bc_rule

每个分片是一个 .npz 文件,里面的数组(n = 这个分片的决策点数):

    obs      (n, 71, 27) uint8   局面编码,见 ai/encoding.py
    oracle   (n, 16, 27) uint8   别人的手牌和牌墙,只给价值头用
    mask     (n, 15)     uint8   115 个动作的合法掩码,按位压缩(np.unpackbits 还原)
    action   (n,)        uint8   老师选的动作编号
    ret      (n,)        int16   从这个决策点到终局,这个座位还会得多少分
    seed     (n,)        int64   哪一局
    seat     (n,)        uint8   哪个座位

只有一个合法动作的局面不记。

--explore 让每个决定有一定概率改成随机走一步。记下来的标签仍然是老师想走的那一步,
这样数据里会有"偏离老师路线之后该怎么办"的局面,学出来的网络自己走偏时不至于不知所措。
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

from chuanma.actions import NUM_ACTIONS
from chuanma.config import RuleConfig
from chuanma.game import NUM_SEATS, Game

from . import AGENTS, make_agent
from .encoding import NUM_CHANNELS, ORACLE_CHANNELS, encode, encode_oracle

FORMAT_VERSION = 1


def play_and_record(
    seed: int, teacher: str, explore: float, config: Optional[RuleConfig], out: dict
) -> None:
    """打一局,把四个座位的决策点追加到 out 的各个列表里。"""
    game = Game(config=config, seed=seed, dealer=seed % NUM_SEATS, record_events=False)
    agents = [make_agent(teacher, seed * 10 + s) for s in range(NUM_SEATS)]
    rng = random.Random(seed ^ 0x5EED)
    start = len(out["action"])
    scores_then: List[int] = []
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
        out["seed"].append(seed)
        out["seat"].append(seat)
        scores_then.append(game.scores[seat])
        if explore and rng.random() < explore:
            choice = rng.choice(legal)
        game.step(choice)
    for k, before in enumerate(scores_then):
        out["ret"].append(game.scores[out["seat"][start + k]] - before)


def _write_shard(job: Tuple[str, int, int, str, float, Optional[dict]]) -> Tuple[int, int]:
    path, first_seed, num_games, teacher, explore, config_dict = job
    config = RuleConfig.from_dict(config_dict) if config_dict else None
    out: dict = {k: [] for k in ("obs", "oracle", "mask", "action", "ret", "seed", "seat")}
    for i in range(num_games):
        play_and_record(first_seed + i, teacher, explore, config, out)
    n = len(out["action"])
    np.savez_compressed(
        path,
        obs=np.stack(out["obs"]) if n else np.zeros((0, NUM_CHANNELS, 27), np.uint8),
        oracle=np.stack(out["oracle"]) if n else np.zeros((0, ORACLE_CHANNELS, 27), np.uint8),
        mask=np.packbits(np.stack(out["mask"]), axis=1) if n else np.zeros((0, 15), np.uint8),
        action=np.asarray(out["action"], dtype=np.uint8),
        ret=np.asarray(out["ret"], dtype=np.int16),
        seed=np.asarray(out["seed"], dtype=np.int64),
        seat=np.asarray(out["seat"], dtype=np.uint8),
    )
    return num_games, n


def generate(
    out_dir: str,
    num_games: int,
    teacher: str = "rule",
    seed: int = 0,
    workers: int = 1,
    shard_games: int = 500,
    explore: float = 0.0,
    config: Optional[RuleConfig] = None,
) -> dict:
    """生成 num_games 局的数据,写到 out_dir。返回写进 meta.json 的那份摘要。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    config_dict = config.to_dict() if config else None
    jobs = []
    for k, first in enumerate(range(0, num_games, shard_games)):
        count = min(shard_games, num_games - first)
        jobs.append((str(out / f"shard_{k:05d}.npz"), seed + first, count, teacher, explore, config_dict))

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
        "config": config_dict or RuleConfig().to_dict(),
        "obs_channels": NUM_CHANNELS,
        "oracle_channels": ORACLE_CHANNELS,
        "seconds": round(seconds, 1),
        "games_per_second": round(num_games / seconds, 1) if seconds else None,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load_shard(path: str) -> dict:
    """读一个分片,把掩码还原成 (n, 115) 的布尔数组。"""
    with np.load(path) as z:
        data = {k: z[k] for k in z.files}
    data["mask"] = np.unpackbits(data["mask"], axis=1)[:, :NUM_ACTIONS].astype(np.bool_)
    return data


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ai.generate", description="生成模仿学习数据")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--games", type=int, default=10000)
    parser.add_argument("--teacher", choices=sorted(AGENTS), default="rule")
    parser.add_argument("--seed", type=int, default=0, help="第一局的种子;评估用的种子要和这里错开")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--shard-games", type=int, default=500, help="每个分片多少局")
    parser.add_argument("--explore", type=float, default=0.0, help="每个决定改成随机走的概率")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    meta = generate(
        args.out, args.games, args.teacher, args.seed, args.workers, args.shard_games, args.explore
    )
    print(
        f"{meta['games']} 局,{meta['samples']} 个决策点,{meta['shards']} 个分片,"
        f"用时 {meta['seconds']} 秒({meta['games_per_second']} 局/秒)→ {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

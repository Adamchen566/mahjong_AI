"""把 Mortal 接进本项目的引擎: 同桌对比,以及把它当老师生成模仿学习数据。

Mortal 的运行时(libriichi,AGPL-3.0)和权重不在仓库里,只在本机 .mortal/ 下(见 docs/riichi-mortal.md)。
本模块只在用到时才导入它们;没有装时报清楚的错,其余代码照常。

    python -m riichi_ai.mortal smoke                                   # 打一场,看转换有没有对不上的地方
    python -m riichi_ai.mortal eval --other shanten --deals 20 --workers 6
    python -m riichi_ai.mortal eval --other checkpoints/riichi_ppo/best.pt --ours --deals 20
    python -m riichi_ai.mortal generate --games 200 --workers 6 --out data/rmortal/a

eval: 同一个种子打 4 次,被测的一方轮流坐 4 个座位,其余三家是另一方(和 riichi_ai.evaluate 一样)。
      默认被测的是 Mortal;加 --ours 则被测的是 --other,其余三家是 Mortal。
generate: 四家都是 Mortal,记下每个有选择的决策点,格式和 riichi_ai.generate 一样,
          另多一列 q(n, 119) float16: Mortal 的 Q 值换算到本项目的动作上,不合法的是 -inf。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from riichi import actions as A
from riichi.actions import Action, NUM_ACTIONS
from riichi.agents import ShantenAgent
from riichi.game import NUM_SEATS, Game, Phase

from .mjai import MjaiConverter, mortal_q_to_ours, reaction_to_action

ROOT = Path(__file__).resolve().parent.parent
MORTAL_DIR = Path(os.environ.get("MORTAL_DIR", ROOT / ".mortal" / "s42"))
MORTAL_SEED = 30_000_000  # 和训练、评估、段位梯的种子都不重叠

_ENGINE = None


def load_engine(device: str = "cpu", threads: int = 1):
    """加载 Mortal(每个进程一次)。"""
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    if not (MORTAL_DIR / "inference.py").is_file():
        raise FileNotFoundError(f"找不到 Mortal: {MORTAL_DIR}(见 docs/riichi-mortal.md 的安装步骤)")
    import torch

    torch.set_num_threads(threads)
    for p in (MORTAL_DIR, MORTAL_DIR / "runtime" / "mortal"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import inference  # type: ignore  # Mortal-S42 自带的加载脚本

    _ENGINE = inference.load_engine(device)
    return _ENGINE


@dataclass
class SeatStats:
    decisions: int = 0
    mismatches: int = 0  # Mortal 的回应在本项目引擎里不合法,或该它决定时它没有回应
    errors: int = 0  # libriichi 不认我们发的事件(转换有错)
    samples: List[str] = field(default_factory=list)  # 前几个对不上的例子

    def add(self, other: "SeatStats") -> None:
        self.decisions += other.decisions
        self.mismatches += other.mismatches
        self.errors += other.errors
        self.samples.extend(other.samples[: max(0, 5 - len(self.samples))])


class MortalSeat:
    """一个座位上的 Mortal。每走一步都要 sync,把新事件转成 mjai 喂给它。"""

    def __init__(self, engine: Any, seat: int, seed: int = 0) -> None:
        from libriichi.mjai import Bot  # type: ignore

        self.seat = seat
        self.bot = Bot(engine, seat)
        self.conv = MjaiConverter(seat)
        self.cursor = 0
        self.reaction: Optional[Dict[str, Any]] = None
        self.broken = False  # 出错之后这一场改由规则型代打
        self.fallback = ShantenAgent(seed)
        self.stats = SeatStats()

    def sync(self, game: Game) -> None:
        events = game.events
        while self.cursor < len(events):
            ev = events[self.cursor]
            self.cursor += 1
            if self.broken:
                continue
            for m in self.conv.convert(ev, game):
                try:
                    raw = self.bot.react(json.dumps(m))
                except Exception as e:  # noqa: BLE001 - libriichi 抛的是普通异常
                    self.broken = True
                    self.stats.errors += 1
                    if len(self.stats.samples) < 5:
                        self.stats.samples.append(f"事件 {m} 出错: {str(e).splitlines()[0][:200]}")
                    break
                # 明杠后的新宝牌在下一张弃牌之后才翻: dahai 的回应(比如碰)不能被紧跟的 dora 冲掉
                if raw or m["type"] != "dora":
                    self.reaction = json.loads(raw) if raw else None

    def act(self, game: Game) -> Tuple[Action, Optional[List[Optional[float]]]]:
        """返回动作和换算后的 Q 值(没有就是 None)。"""
        legal = game.legal_actions()
        self.stats.decisions += 1
        if self.broken:
            return self.fallback.act(game.observation(self.seat), legal), None
        a = reaction_to_action(self.reaction, game)
        if a is None:
            self.stats.mismatches += 1
            if len(self.stats.samples) < 5:
                self.stats.samples.append(
                    f"阶段 {game.phase.name},合法 {[str(x) for x in legal]},Mortal 回应 {self.reaction}"
                )
            a = A.PASS if A.PASS in legal else self.fallback.act(game.observation(self.seat), legal)
            return a, None
        q = mortal_q_to_ours((self.reaction or {}).get("meta"), legal)
        return a, q


def play(
    seed: int,
    seats: Sequence[str],
    record: Optional[dict] = None,
    device: str = "cpu",
) -> Tuple[Game, SeatStats]:
    """打一场。seats[i] 是 "mortal" 或 riichi_ai.make_agent 认的名字。record 不为空时记下 Mortal 的决策点。"""
    from . import make_agent

    engine = load_engine(device)
    mortal: Dict[int, MortalSeat] = {}
    agents: Dict[int, Any] = {}
    for s, name in enumerate(seats):
        if name == "mortal":
            mortal[s] = MortalSeat(engine, s, seed * 10 + s)
        else:
            agents[s] = make_agent(name, seed * 10 + s)
    game = Game(seed=seed, record_events=True)
    then: List[Tuple[int, int]] = []
    for m in mortal.values():
        m.sync(game)
    while not game.is_over:
        s = game.current
        legal = game.legal_actions()
        if s in mortal:
            choice, q = mortal[s].act(game)
            if record is not None and len(legal) > 1 and q is not None:
                _record(record, game, s, legal, choice, q)
                then.append((s, game.scores[s]))
        elif len(legal) == 1:
            choice = legal[0]
        else:
            choice = agents[s].act(game.observation(s), legal)
        game.step(choice)
        for m in mortal.values():
            m.sync(game)
    if record is not None:
        from .generate import remaining_value

        for s, score in then:
            record["ret"].append(remaining_value(game, s, score))
    stats = SeatStats()
    for m in mortal.values():
        stats.add(m.stats)
    return game, stats


def _record(out: dict, game: Game, seat: int, legal: List[Action], choice: Action, q: List[Optional[float]]) -> None:
    from .encoding import danger_labels, encode, encode_oracle

    out["obs"].append(encode(game, seat))
    out["oracle"].append(encode_oracle(game, seat))
    mask = np.zeros(NUM_ACTIONS, dtype=np.bool_)
    mask[[a.id for a in legal]] = True
    out["mask"].append(mask)
    out["action"].append(choice.id)
    has = game.phase == Phase.TURN and game.drawn is not None
    out["danger"].append(danger_labels(game, seat) if has else np.zeros(34, np.uint8))
    out["has_danger"].append(1 if has else 0)
    out["seed"].append(game.seed)
    out["seat"].append(seat)
    out["q"].append(np.asarray([-np.inf if v is None else v for v in q], dtype=np.float16))


# ---------------------------------------------------------------------- 同桌对比


def _eval_deal(job: Tuple[str, bool, int]) -> Tuple[Any, SeatStats]:
    from .evaluate import DealResult

    other, ours, seed = job
    out = DealResult(points=[], ranks=[])
    total = SeatStats()
    for seat in range(NUM_SEATS):
        rest, me = ("mortal", other) if ours else (other, "mortal")
        seats = [rest] * NUM_SEATS
        seats[seat] = me
        game, st = play(seed, seats)
        total.add(st)
        out.points.append(game.final_points()[seat])
        out.ranks.append(game.ranks()[seat])
        out.hands += len(game.hand_results)
        for r in game.hand_results:
            for w in r.get("wins", []):
                if w["seat"] == seat:
                    out.wins += 1
                elif w["from_seat"] == seat:
                    out.deal_ins += 1
    return out, total


def evaluate(other: str, ours: bool, deals: int, seed: int = MORTAL_SEED, workers: int = 1):
    from .evaluate import EvalResult

    jobs = [(other, ours, seed + i) for i in range(deals)]
    start = time.perf_counter()
    if workers > 1:
        with Pool(workers) as pool:
            results = pool.map(_eval_deal, jobs, chunksize=1)
    else:
        results = [_eval_deal(j) for j in jobs]
    cand, base = (other, "Mortal") if ours else ("Mortal", other)
    res = EvalResult(cand, base, deals, time.perf_counter() - start)
    stats = SeatStats()
    for d, st in results:
        res.deal_means.append(sum(d.points) / NUM_SEATS)
        res.rank_sum += sum(d.ranks)
        res.hands += d.hands
        res.wins += d.wins
        res.deal_ins += d.deal_ins
        stats.add(st)
    return res, stats


# ---------------------------------------------------------------------- 生成蒸馏数据


def _gen_shard(job: Tuple[str, int, int]) -> Tuple[int, int, SeatStats]:
    from .encoding import NUM_CHANNELS, ORACLE_CHANNELS
    from .generate import MASK_BYTES

    path, first, count = job
    keys = ("obs", "oracle", "mask", "action", "ret", "danger", "has_danger", "seed", "seat", "q")
    out: dict = {k: [] for k in keys}
    stats = SeatStats()
    for i in range(count):
        _, st = play(first + i, ["mortal"] * NUM_SEATS, record=out)
        stats.add(st)
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
        q=np.stack(out["q"]) if n else np.zeros((0, NUM_ACTIONS), np.float16),
    )
    return count, n, stats


def generate(out_dir: str, games: int, seed: int, workers: int, shard_games: int) -> dict:
    from .encoding import NUM_CHANNELS, ORACLE_CHANNELS
    from .generate import FORMAT_VERSION

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [
        (str(out / f"shard_{k:05d}.npz"), seed + first, min(shard_games, games - first))
        for k, first in enumerate(range(0, games, shard_games))
    ]
    start = time.perf_counter()
    if workers > 1:
        with Pool(workers) as pool:
            results = pool.map(_gen_shard, jobs, chunksize=1)
    else:
        results = [_gen_shard(j) for j in jobs]
    seconds = time.perf_counter() - start
    stats = SeatStats()
    for _, _, st in results:
        stats.add(st)
    meta = {
        "format_version": FORMAT_VERSION,
        "teacher": "mortal-s42",
        "games": games,
        "samples": sum(n for _, n, _ in results),
        "shards": len(jobs),
        "seed": seed,
        "explore": 0.0,
        "obs_channels": NUM_CHANNELS,
        "oracle_channels": ORACLE_CHANNELS,
        "seconds": round(seconds, 1),
        "games_per_second": round(games / seconds, 3) if seconds else None,
        "decisions": stats.decisions,
        "mismatches": stats.mismatches,
        "errors": stats.errors,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**meta, "examples": stats.samples}


# ---------------------------------------------------------------------- 命令行


def _print_stats(stats: SeatStats) -> None:
    print(f"  Mortal 决定 {stats.decisions} 次,对不上 {stats.mismatches} 次,事件出错 {stats.errors} 次")
    for s in stats.samples:
        print("   ", s)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m riichi_ai.mortal", description="Mortal 同桌对比和蒸馏数据")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("smoke", help="Mortal 和三个规则型打一场")
    p.add_argument("--seed", type=int, default=MORTAL_SEED)
    p.add_argument("--all", action="store_true", help="四家都是 Mortal")
    p = sub.add_parser("eval", help="同桌对比")
    p.add_argument("--other", default="shanten", help="另一方: 登记表里的名字或模型文件")
    p.add_argument("--ours", action="store_true", help="被测的是 --other,其余三家是 Mortal")
    p.add_argument("--deals", type=int, default=20)
    p.add_argument("--seed", type=int, default=MORTAL_SEED)
    p.add_argument("--workers", type=int, default=1)
    p = sub.add_parser("generate", help="四家 Mortal,生成蒸馏数据")
    p.add_argument("--out", required=True)
    p.add_argument("--games", type=int, default=100)
    p.add_argument("--seed", type=int, default=MORTAL_SEED + 1_000_000)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--shard-games", type=int, default=10)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    if args.cmd == "smoke":
        seats = ["mortal"] * 4 if args.all else ["mortal", "shanten", "shanten", "shanten"]
        t = time.perf_counter()
        game, stats = play(args.seed, seats)
        sec = time.perf_counter() - t
        print(f"打完一场({len(game.hand_results)} 局,{sec:.1f} 秒),终局点数 {game.scores},名次分 {game.final_points()}")
        _print_stats(stats)
    elif args.cmd == "eval":
        res, stats = evaluate(args.other, args.ours, args.deals, args.seed, args.workers)
        print(res.summary())
        _print_stats(stats)
    else:
        meta = generate(args.out, args.games, args.seed, args.workers, args.shard_games)
        print(
            f"{meta['games']} 场半庄,{meta['samples']} 个决策点,用时 {meta['seconds']} 秒;"
            f"对不上 {meta['mismatches']} / {meta['decisions']},出错 {meta['errors']}"
        )
        for s in meta["examples"]:
            print("   ", s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

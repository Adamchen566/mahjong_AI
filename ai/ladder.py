"""段位梯: 各个版本两两同桌对打,生成界面"AI 段位梯"页面用的数据。

    python -m ai.ladder --deals 2500 --workers 12

每一对 (甲, 乙) 用同牌对比: 同一副牌打 4 次,甲轮流坐 4 个座位,其余三家都是乙。
结果是"甲和三个乙同桌时平均每局得多少分"和 95% 置信区间,写进 models/ladder.json。
用的牌和训练、定期评估都不重叠(种子从 LADDER_SEED 起),所以这里的成绩也是
"拿没见过的牌再确认一遍"。

模型存档(.pt)会先导出成 ONNX 放在 checkpoints/ladder/ 下,对打时用 onnxruntime,
每个进程只加载一次。跑到一半中断了可以加 --resume 接着跑。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chuanma.agents import Agent
from chuanma.game import NUM_SEATS
from chuanma.runner import play_game

from . import AGENTS, make_agent

LADDER_SEED = 20_000_000  # 不和训练数据(0 起)、定期评估(1000 万起)、自我对弈(1 亿起)的种子重叠
ROOT = Path(__file__).resolve().parent.parent

# (编号, 名字, 说明, 来源)。来源是登记表里的名字,或相对项目目录的模型存档;存档不存在的那一项跳过
DEFAULT_PLAYERS: List[Tuple[str, str, str, str]] = [
    ("simple", "简单", "能碰就碰,丢最孤立的牌", "simple"),
    ("rule", "规则型", "算向听数和进张", "rule"),
    ("bc", "模仿模型", "只学了规则型的打法", "checkpoints/bc/best.pt"),
    ("ppo-early", "自我对弈初期", "自我对弈刚开始不久", "checkpoints/ppo_trial/latest.pt"),
    ("ppo-best", "自我对弈", "定期评估里成绩最好的一版", "checkpoints/ppo/best.pt"),
]

_CACHE: Dict[str, Agent] = {}


def _agent(source: str, seed: int) -> Agent:
    """规则类策略每局新建(便宜,而且有的带随机数);模型每个进程只加载一次(它不带状态)。"""
    if source in AGENTS:
        return make_agent(source, seed)
    if source not in _CACHE:
        _CACHE[source] = make_agent(source)
    return _CACHE[source]


def play_deal(args: Tuple[str, str, int]) -> Tuple[float, int, int]:
    """一副牌打 4 次,返回 (甲的平均得分, 甲胡牌次数, 甲点炮次数)。"""
    cand, base, seed = args
    total = wins = deal_ins = 0
    for seat in range(NUM_SEATS):
        agents = [_agent(base, seed * 10 + s) for s in range(NUM_SEATS)]
        agents[seat] = _agent(cand, seed * 10 + seat)
        game = play_game(agents, seed=seed, dealer=seed % NUM_SEATS)
        total += game.scores[seat]
        for w in game.wins:
            wins += w.seat == seat
            deal_ins += w.seat != seat and w.from_seat == seat
    return total / NUM_SEATS, wins, deal_ins


def summarize(rows: List[Tuple[float, int, int]]) -> Dict[str, float]:
    n = len(rows)
    means = [r[0] for r in rows]
    mean = sum(means) / n
    var = sum((x - mean) ** 2 for x in means) / (n - 1)
    half = 1.96 * math.sqrt(var / n)
    games = n * NUM_SEATS
    return {
        "mean": round(mean, 4),
        "lo": round(mean - half, 4),
        "hi": round(mean + half, 4),
        "win_rate": round(sum(r[1] for r in rows) / games, 4),
        "deal_in_rate": round(sum(r[2] for r in rows) / games, 4),
    }


def read_curve(log_path: Path) -> List[Dict[str, float]]:
    """训练日志里的定期评估: 累计局数 -> 对三个规则型 AI 的成绩。"""
    if not log_path.is_file():
        return []
    out = []
    with log_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("eval_score"):
                out.append(
                    {
                        "games": int(row["games"]),
                        "score": float(row["eval_score"]),
                        "lo": float(row["eval_lo"]),
                        "hi": float(row["eval_hi"]),
                        "deal_in_rate": float(row["eval_deal_in_rate"]),
                    }
                )
    return out


def prepare(players: List[Tuple[str, str, str, str]], work_dir: Path) -> List[Dict[str, Any]]:
    """把模型存档导出成 ONNX,返回实际参赛的选手。"""
    out = []
    for pid, label, note, source in players:
        entry: Dict[str, Any] = {"id": pid, "label": label, "note": note, "games": None}
        if source in AGENTS:
            entry["source"] = source
        else:
            ckpt = ROOT / source
            if not ckpt.is_file():
                print(f"跳过 {label}: 找不到 {source}", flush=True)
                continue
            from .export import export_onnx
            from .model import load_checkpoint

            state = load_checkpoint(ckpt).get("state") or {}
            if state.get("games"):
                entry["games"] = int(state["games"])
                entry["note"] = f"{note},练了 {state['games'] / 1e4:.0f} 万局"
            onnx = work_dir / f"{pid}.onnx"
            export_onnx(str(ckpt), str(onnx))
            entry["source"] = str(onnx)
        out.append(entry)
    return out


def run(
    deals: int,
    workers: int,
    out_path: Path,
    players: Optional[List[Tuple[str, str, str, str]]] = None,
    log_path: Optional[Path] = None,
    resume: bool = False,
    seed: int = LADDER_SEED,
) -> Dict[str, Any]:
    entries = prepare(players or DEFAULT_PLAYERS, ROOT / "checkpoints" / "ladder")
    n = len(entries)
    ids = [e["id"] for e in entries]
    matrix: List[List[Optional[Dict[str, float]]]] = [[None] * n for _ in range(n)]
    if resume and out_path.is_file():
        old = json.loads(out_path.read_text(encoding="utf-8"))
        if old.get("games_per_pair") == deals * NUM_SEATS and old.get("seed") == seed:
            old_ids = [p["id"] for p in old.get("players", [])]
            for i, a in enumerate(ids):
                for j, b in enumerate(ids):
                    if a in old_ids and b in old_ids:
                        matrix[i][j] = old["matrix"][old_ids.index(a)][old_ids.index(b)]

    def save() -> Dict[str, Any]:
        data = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "seed": seed,
            "games_per_pair": deals * NUM_SEATS,
            "players": [{k: e[k] for k in ("id", "label", "note", "games")} for e in entries],
            "matrix": matrix,
            "curve": read_curve(log_path or ROOT / "checkpoints" / "ppo" / "log.csv"),
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        return data

    todo = [(i, j) for i in range(n) for j in range(n) if i != j and matrix[i][j] is None]
    print(f"{n} 个选手,还要打 {len(todo)} 对,每对 {deals} 副牌 × 4 局", flush=True)
    data = save()
    with Pool(workers) as pool:
        for k, (i, j) in enumerate(todo, 1):
            start = time.perf_counter()
            jobs = [(entries[i]["source"], entries[j]["source"], seed + d) for d in range(deals)]
            rows = pool.map(play_deal, jobs, chunksize=max(1, deals // (workers * 8)))
            matrix[i][j] = summarize(rows)
            data = save()
            cell = matrix[i][j]
            print(
                f"[{k}/{len(todo)}] {entries[i]['label']} 对 3 个{entries[j]['label']}: "
                f"{cell['mean']:+.3f} [{cell['lo']:+.3f}, {cell['hi']:+.3f}],"
                f"点炮率 {cell['deal_in_rate']:.1%},用时 {time.perf_counter() - start:.0f} 秒",
                flush=True,
            )
    return data


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ai.ladder", description="各个版本两两对打,生成段位梯的数据")
    parser.add_argument("--deals", type=int, default=2500, help="每一对打多少副牌(每副 4 局)")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--out", default=str(ROOT / "models" / "ladder.json"))
    parser.add_argument("--resume", action="store_true", help="接着上次没打完的继续")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run(args.deals, args.workers, Path(args.out), resume=args.resume)
    print(f"已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

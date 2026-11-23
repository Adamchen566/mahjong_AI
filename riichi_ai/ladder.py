"""日麻段位梯: 各个版本两两同牌对比,结果写进 models/riichi_ladder.json。

    python -m riichi_ai.ladder --deals 300 --workers 12

每一对 (甲, 乙): 同一个种子的半庄打 4 次,甲轮流坐 4 个座位,其余三家都是乙。
结果是"甲和三个乙同桌时的平均名次分"和 95% 区间。种子从 LADDER_SEED 起,和训练、定期评估都不重叠。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .evaluate import evaluate

LADDER_SEED = 20_000_000
ROOT = Path(__file__).resolve().parent.parent

# (编号, 名字, 说明, 来源);来源是登记表里的名字或相对项目目录的模型存档,不存在的跳过
DEFAULT_PLAYERS: List[Tuple[str, str, str, str]] = [
    ("simple", "简单", "不吃不碰不立直,丢最孤立的牌", "simple"),
    ("shanten", "规则型", "向听数 + 进张,听牌就立直", "shanten"),
    ("bc", "模仿模型", "只学了规则型的打法", "checkpoints/riichi_bc/best.pt"),
    ("ppo", "自我对弈", "定期评估里成绩最好的一版", "checkpoints/riichi_ppo/best.pt"),
    ("mortal_bc", "学过 Mortal", "从自我对弈出发,学了 Mortal 的选择和 Q 值", "checkpoints/riichi_mortal_bc/best.pt"),
]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m riichi_ai.ladder", description="日麻段位梯")
    parser.add_argument("--deals", type=int, default=300)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--out", default=str(ROOT / "models" / "riichi_ladder.json"))
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    players = []
    for pid, name, note, source in DEFAULT_PLAYERS:
        path = source if not source.endswith(".pt") else str(ROOT / source)
        if source.endswith(".pt") and not Path(path).is_file():
            print(f"跳过 {name}: 找不到 {source}")
            continue
        players.append({"id": pid, "name": name, "note": note, "source": path})
    n = len(players)
    matrix: List[List[Optional[dict]]] = [[None] * n for _ in range(n)]
    for i, a in enumerate(players):
        for j, b in enumerate(players):
            if i == j:
                continue
            r = evaluate(a["source"], b["source"], args.deals, seed=LADDER_SEED, workers=args.workers)
            lo, hi = r.ci95
            matrix[i][j] = {
                "points": round(r.mean, 3),
                "lo": round(lo, 3),
                "hi": round(hi, 3),
                "avg_rank": round(r.avg_rank, 4),
                "win_rate": round(r.wins / max(r.hands, 1), 4),
                "deal_in_rate": round(r.deal_ins / max(r.hands, 1), 4),
                "games": r.games,
            }
            print(f"{a['name']} 对 3 个 {b['name']}: {r.mean:+.2f} [{lo:+.2f}, {hi:+.2f}],平均顺位 {r.avg_rank:.3f}")
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "deals": args.deals,
        "seed": LADDER_SEED,
        "players": [{k: p[k] for k in ("id", "name", "note")} for p in players],
        "matrix": matrix,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写好了 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""命令行入口。

    python -m riichi play --seed 1                 # 四个 ShantenAgent 打一场半庄,打印过程
    python -m riichi play --agents shanten,simple,random,shanten
    python -m riichi simulate -n 200               # 批量对局,看速度和统计
"""
from __future__ import annotations

import argparse
import sys
from typing import List

from .agents import AGENTS, make_agent
from .game import NUM_SEATS
from .record import GameRecord
from .runner import play_game, simulate
from .tiles import WIND_NAMES, tile_name, tiles_str

ROUND_NAMES = ("东", "南", "西", "北")
REASONS = {
    "exhaustive": "荒牌流局",
    "nagashi_mangan": "流局满贯",
    "kyuushu": "九种九牌",
    "suufon_renda": "四风连打",
    "suukaikan": "四杠散了",
    "suucha_riichi": "四家立直",
    "sanchahou": "三家和",
}
END_REASONS = {
    "finished": "打完",
    "dealer_top": "庄家止和",
    "tobi": "击飞",
    "overtime_target": "西入后有人到返点",
    "overtime_over": "延长场打完",
    "one_hand": "只打一局",
}


def _agents(spec: str, seed: int):
    names = spec.split(",")
    if len(names) == 1:
        names = names * NUM_SEATS
    if len(names) != NUM_SEATS or any(n not in AGENTS for n in names):
        raise SystemExit(f"--agents 要写 1 个或 4 个名字,可选 {', '.join(AGENTS)}")
    return [make_agent(n, seed + s) for s, n in enumerate(names)]


def _hand_line(r: dict) -> List[str]:
    title = f"{ROUND_NAMES[r['round_wind'] % 4]}{r['kyoku'] + 1}局 {r['honba']}本场"
    out = []
    if r["type"] == "win":
        for w in r["wins"]:
            how = "自摸" if w["tsumo"] else f"荣和 座位{w['from_seat']}"
            value = w["limit"] or f"{w['han']}番{w['fu']}符"
            if w["yakuman"]:
                value = w["limit"]
            yaku = "、".join(f"{n}{'' if w['yakuman'] else h}" for n, h in w["yaku"])
            out.append(
                f"{title}: 座位{w['seat']} {how} {tile_name(w['tile'])}  {value}  +{w['gain']}  [{yaku}]"
                f"  手牌 {tiles_str(w['hand'])}"
            )
    else:
        tenpai = r.get("tenpai")
        extra = ""
        if tenpai is not None:
            extra = " 听牌: " + ("".join(str(s) for s in range(4) if tenpai[s]) or "无")
        out.append(f"{title}: {REASONS[r['reason']]}{extra}")
    out.append("    点数 " + " ".join(f"{s}:{v}({d:+d})" for s, (v, d) in enumerate(zip(r["scores"], r["deltas"]))))
    return out


def cmd_play(args) -> int:
    game = play_game(_agents(args.agents, args.seed), seed=args.seed, record_events=args.verbose)
    if args.verbose:
        for ev in game.events:
            if ev["type"] in ("riichi_accepted", "pon", "chi", "kan"):
                print(f"  {ev}")
    for r in game.hand_results:
        for line in _hand_line(r):
            print(line)
    res = game.result()
    print(f"\n结束({END_REASONS[res['end_reason']]}),共 {res['hands']} 局")
    for s in range(NUM_SEATS):
        print(f"  座位 {s}: {res['scores'][s]} 点,第 {res['ranks'][s] + 1} 名,名次分 {res['final_points'][s]:+.1f}")
    if args.save:
        GameRecord.from_game(game).save(args.save)
        print(f"牌谱已保存到 {args.save}")
    return 0


def cmd_simulate(args) -> int:
    print(simulate(_agents(args.agents, args.seed), args.num_games, seed=args.seed).summary())
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m riichi", description="日本麻将规则引擎")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("play", help="打一场半庄并打印每一局的结果")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agents", default="shanten", help="一个名字或逗号分隔的四个名字")
    p.add_argument("--save", help="把牌谱保存到这个文件")
    p.add_argument("-v", "--verbose", action="store_true", help="同时打印立直和吃碰杠")
    p.set_defaults(func=cmd_play)
    q = sub.add_parser("simulate", help="批量对局统计")
    q.add_argument("-n", "--num-games", type=int, default=100)
    q.add_argument("--seed", type=int, default=0)
    q.add_argument("--agents", default="shanten")
    q.set_defaults(func=cmd_simulate)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

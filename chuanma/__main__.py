"""命令行入口。

    python -m chuanma play --seed 1          # 四个 SimpleAgent 打一局,打印过程
    python -m chuanma simulate -n 2000       # 批量对局,看速度和统计
"""
from __future__ import annotations

import argparse
import sys
from typing import List

from .agents import Agent, RandomAgent, SimpleAgent
from .game import NUM_SEATS
from .record import GameRecord
from .runner import play_game, simulate
from .tiles import SUIT_NAMES, tile_name, tiles_str

SEAT_NAMES = ("东", "南", "西", "北")
DIRECTIONS = {1: "下家", 2: "对家", 3: "上家"}


def _make_agents(kind: str, seed: int) -> List[Agent]:
    cls = {"simple": SimpleAgent, "random": RandomAgent}[kind]
    return [cls(seed + s) for s in range(NUM_SEATS)]


def _describe(ev: dict) -> str:
    t = ev["type"]
    seat = SEAT_NAMES[ev["seat"]] if "seat" in ev else ""
    if t == "deal":
        return f"发牌,庄家 {SEAT_NAMES[ev['dealer']]}"
    if t == "exchange":
        return f"换三张,方向: 给{DIRECTIONS[ev['direction']]}"
    if t == "void":
        return "定缺: " + " ".join(f"{SEAT_NAMES[s]}缺{SUIT_NAMES[v]}" for s, v in enumerate(ev["voids"]))
    if t == "draw":
        return f"{seat} 摸 {tile_name(ev['tile'])}" + ("(杠后补牌)" if ev["after_gang"] else "")
    if t == "discard":
        return f"{seat} 打 {tile_name(ev['tile'])}"
    if t == "pong":
        return f"{seat} 碰 {tile_name(ev['tile'])}"
    if t == "gang_declared":
        return f"{seat} 宣布加杠 {tile_name(ev['tile'])},等待抢杠"
    if t == "gang":
        label = {"AN_GANG": "暗杠", "JIA_GANG": "加杠", "MING_GANG": "直杠"}[ev["kind"]]
        return f"{seat} {label} {tile_name(ev['tile'])}"
    if t == "hu":
        how = "自摸" if ev["zimo"] else f"胡 {SEAT_NAMES[ev['from_seat']]} 的"
        tile = tile_name(ev["tile"]) if ev["tile"] is not None else ""
        return f"★ {seat} {how}{tile}: {'/'.join(ev['names'])},{ev['fan']} 番,每家 {ev['points']} 分"
    if t == "transfer":
        return f"    {SEAT_NAMES[ev['payer']]} → {SEAT_NAMES[ev['payee']]} {ev['amount']} 分 ({ev['note']})"
    if t == "end":
        reason = {"three_won": "三家已胡", "wall_exhausted": "牌墙摸完"}[ev["reason"]]
        return f"结束({reason}),得分: " + " ".join(
            f"{SEAT_NAMES[s]} {v:+d}" for s, v in enumerate(ev["scores"])
        )
    return str(ev)


def cmd_play(args: argparse.Namespace) -> int:
    game = play_game(_make_agents(args.agents, args.seed), seed=args.seed, record_events=True)
    for ev in game.events:
        print(_describe(ev))
    print("\n终局手牌:")
    for s in range(NUM_SEATS):
        melds = " ".join(f"[{m.type.name} {tile_name(m.tile)}]" for m in game.melds[s])
        status = "已胡" if game.won[s] else "未胡"
        print(f"  {SEAT_NAMES[s]} ({status}): {tiles_str(game.hand_tiles(s))} {melds}")
    if args.save:
        GameRecord.from_game(game).save(args.save)
        print(f"\n牌谱已保存到 {args.save}")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    stats = simulate(_make_agents(args.agents, args.seed), args.num_games, seed=args.seed)
    print(stats.summary())
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m chuanma", description="四川麻将规则引擎")
    sub = parser.add_subparsers(dest="command", required=True)

    p_play = sub.add_parser("play", help="打一局并打印过程")
    p_play.add_argument("--seed", type=int, default=0)
    p_play.add_argument("--agents", choices=("simple", "random"), default="simple")
    p_play.add_argument("--save", help="把牌谱保存到这个文件")
    p_play.set_defaults(func=cmd_play)

    p_sim = sub.add_parser("simulate", help="批量对局统计")
    p_sim.add_argument("-n", "--num-games", type=int, default=1000)
    p_sim.add_argument("--seed", type=int, default=0)
    p_sim.add_argument("--agents", choices=("simple", "random"), default="simple")
    p_sim.set_defaults(func=cmd_simulate)

    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

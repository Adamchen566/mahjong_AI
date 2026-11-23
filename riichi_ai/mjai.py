"""本项目引擎的事件流 ↔ mjai 协议(Mortal 等外部 AI 用的格式)。

只做格式转换,不依赖任何外部代码,可以单独测试。

    conv = MjaiConverter(seat)
    for ev in game.events[cursor:]:
        for m in conv.convert(ev, game):   # 0 个或多个 mjai 事件(dict)
            ...
    action = reaction_to_action(reaction, game)   # mjai 的回应 → 本项目的 Action

对应关系:

| 本项目 | mjai |
|---|---|
| 开局(第一个 hand_start 之前) | start_game |
| hand_start | start_kyoku(别家的配牌写成 "?") |
| draw | tsumo(别家摸的牌写成 "?") |
| discard | dahai |
| riichi / riichi_accepted | reach / reach_accepted |
| chi / pon | chi / pon |
| kan(大明杠、暗杠) | daiminkan / ankan |
| kan_declared(加杠宣言) | kakan;之后的 kan(加杠完成)不再发 |
| dora | dora |
| hand_end | hora(每个和牌的人一条)或 ryukyoku,再加 end_kyoku |
| game_end | end_game |
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from riichi import actions as A
from riichi.actions import Action, ActionType
from riichi.game import DEAL_SIZE, NUM_SEATS, Game, Phase
from riichi.tiles import kind_of

_HONORS = "ESWNPFC"
_SUITS = "mps"
WINDS = "ESWN"


def tile_to_mjai(t: int) -> str:
    if t >= 34:
        return f"5{_SUITS[t - 34]}r"
    if t >= 27:
        return _HONORS[t - 27]
    return f"{t % 9 + 1}{_SUITS[t // 9]}"


def mjai_to_tile(s: str) -> int:
    if len(s) == 1:
        return 27 + _HONORS.index(s)
    if s.endswith("r"):
        return 34 + _SUITS.index(s[1])
    return _SUITS.index(s[1]) * 9 + int(s[0]) - 1


class MjaiConverter:
    """一个座位视角的转换器。按顺序喂本项目的事件,吐出 mjai 事件。"""

    def __init__(self, seat: int) -> None:
        self.seat = seat
        self.started = False
        self.hands_seen = 0

    def convert(self, ev: Dict[str, Any], game: Game) -> List[Dict[str, Any]]:
        t = ev["type"]
        out: List[Dict[str, Any]] = []
        if not self.started:
            out.append({"type": "start_game", "names": ["p0", "p1", "p2", "p3"]})
            self.started = True
        if t == "hand_start":
            wall = game.walls_used[self.hands_seen]
            self.hands_seen += 1
            tehais = []
            for s in range(NUM_SEATS):
                if s == self.seat:
                    tehais.append([tile_to_mjai(x) for x in wall[s * DEAL_SIZE : (s + 1) * DEAL_SIZE]])
                else:
                    tehais.append(["?"] * DEAL_SIZE)
            out.append(
                {
                    "type": "start_kyoku",
                    "bakaze": WINDS[ev["round_wind"] % 4],
                    "dora_marker": tile_to_mjai(ev["dora_indicator"]),
                    "kyoku": ev["kyoku"] + 1,
                    "honba": ev["honba"],
                    "kyotaku": ev["sticks"],
                    "oya": ev["dealer"],
                    "scores": list(ev["scores"]),
                    "tehais": tehais,
                }
            )
        elif t == "draw":
            pai = tile_to_mjai(ev["tile"]) if ev["seat"] == self.seat else "?"
            out.append({"type": "tsumo", "actor": ev["seat"], "pai": pai})
        elif t == "discard":
            out.append(
                {"type": "dahai", "actor": ev["seat"], "pai": tile_to_mjai(ev["tile"]), "tsumogiri": bool(ev["tsumogiri"])}
            )
        elif t == "riichi":
            out.append({"type": "reach", "actor": ev["seat"]})
        elif t == "riichi_accepted":
            out.append({"type": "reach_accepted", "actor": ev["seat"]})
        elif t in ("chi", "pon"):
            out.append(
                {
                    "type": t,
                    "actor": ev["seat"],
                    "target": ev["from_seat"],
                    "pai": tile_to_mjai(ev["tile"]),
                    "consumed": [tile_to_mjai(x) for x in ev["tiles"][1:]],
                }
            )
        elif t == "kan":
            if ev["kind"] == "DAIMINKAN":
                out.append(
                    {
                        "type": "daiminkan",
                        "actor": ev["seat"],
                        "target": ev["from_seat"],
                        "pai": tile_to_mjai(ev["tile"]),
                        "consumed": [tile_to_mjai(x) for x in ev["tiles"][1:]],
                    }
                )
            elif ev["kind"] == "ANKAN":
                out.append({"type": "ankan", "actor": ev["seat"], "consumed": [tile_to_mjai(x) for x in ev["tiles"]]})
            # KAKAN 在宣言时已经发过
        elif t == "kan_declared":
            s, tile = ev["seat"], ev["tile"]
            k = kind_of(tile)
            # 要在这一步之后立刻转换(那时碰已经变成加杠,前三张是原来的碰)
            pon = next(m for m in game.melds[s] if m.type.name in ("PON", "KAKAN") and kind_of(m.tiles[0]) == k)
            out.append(
                {
                    "type": "kakan",
                    "actor": s,
                    "pai": tile_to_mjai(tile),
                    "consumed": [tile_to_mjai(x) for x in pon.tiles[:3]],
                }
            )
        elif t == "dora":
            out.append({"type": "dora", "dora_marker": tile_to_mjai(ev["indicator"])})
        elif t == "hand_end":
            r = ev["result"]
            if r["type"] == "win":
                for w in r["wins"]:
                    target = w["seat"] if w["tsumo"] else w["from_seat"]
                    out.append({"type": "hora", "actor": w["seat"], "target": target})
            else:
                out.append({"type": "ryukyoku"})
            out.append({"type": "end_kyoku"})
        elif t == "game_end":
            out.append({"type": "end_game"})
        return out


def reaction_to_action(r: Optional[Dict[str, Any]], game: Game) -> Optional[Action]:
    """mjai 的回应 → 本项目的动作。对不上(规则差异)时返回 None,由调用方兜底。"""
    legal = game.legal_actions()
    if r is None:
        return None
    t = r.get("type")
    cand: List[Action] = []
    if t == "dahai":
        tile = mjai_to_tile(r["pai"])
        cand = [A.discard(tile)]
        if tile >= 34:
            cand.append(A.discard(kind_of(tile)))
        elif kind_of(tile) in (4, 13, 22):
            cand.append(A.discard(34 + tile // 9))
    elif t == "reach":
        cand = [A.RIICHI]
    elif t == "hora":
        cand = [A.TSUMO] if game.phase == Phase.TURN else [A.RON]
    elif t == "ryukyoku":
        cand = [A.KYUUSHU]
    elif t == "none":
        cand = [A.PASS]
    elif t == "pon":
        red = any(c.endswith("r") for c in r["consumed"])
        cand = [A.pon(red), A.pon(not red)]
    elif t == "chi":
        k = kind_of(mjai_to_tile(r["pai"]))
        used = sorted(kind_of(mjai_to_tile(c)) for c in r["consumed"])
        shape = 0 if used[0] > k else (2 if used[1] < k else 1)
        red = any(c.endswith("r") for c in r["consumed"])
        cand = [A.chi(shape, red), A.chi(shape, not red)]
    elif t == "daiminkan":
        cand = [A.DAIMINKAN]
    elif t == "ankan":
        cand = [A.ankan(kind_of(mjai_to_tile(r["consumed"][0])))]
    elif t == "kakan":
        cand = [A.kakan(kind_of(mjai_to_tile(r["pai"])))]
    for a in cand:
        if a in legal:
            return a
    return None


# Mortal 的 46 个动作 → 本项目的动作(用来把 Q 值换算到 119 个动作上)
MORTAL_ACTIONS = 46


def mortal_index_to_actions(i: int) -> List[Action]:
    """Mortal 动作编号可能对应的本项目动作(吃碰的赤 5、杠的种类在 Mortal 里不区分)。"""
    if i < 34:
        return [A.discard(i)]
    if i < 37:
        return [A.discard(i)]  # 34..36 赤 5,编号恰好一样
    if i == 37:
        return [A.RIICHI]
    if i <= 40:
        return [A.chi(i - 38, False), A.chi(i - 38, True)]
    if i == 41:
        return [A.pon(False), A.pon(True)]
    if i == 42:
        return [A.DAIMINKAN] + [A.ankan(k) for k in range(34)] + [A.kakan(k) for k in range(34)]
    if i == 43:
        return [A.TSUMO, A.RON]
    if i == 44:
        return [A.KYUUSHU]
    return [A.PASS]


def mortal_q_to_ours(meta: Optional[Dict[str, Any]], legal: List[Action]) -> Optional[List[float]]:
    """把回应里 meta 的 Q 值(按 mask_bits 压缩的合法动作顺序)摊到本项目 119 个动作上;不合法的是 None。"""
    if not meta or "q_values" not in meta or "mask_bits" not in meta:
        return None
    bits = int(meta["mask_bits"])
    idx = [i for i in range(MORTAL_ACTIONS) if bits >> i & 1]
    q = meta["q_values"]
    if len(idx) != len(q):
        return None
    legal_ids = {a.id for a in legal}
    out: List[Optional[float]] = [None] * A.NUM_ACTIONS
    for i, v in zip(idx, q):
        for a in mortal_index_to_actions(i):
            if a.id in legal_ids:
                out[a.id] = float(v)
    return out

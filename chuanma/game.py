"""四川麻将(血战到底)规则引擎。

Game 是一个纯状态机: 不打印、不读输入、不联网。用法只有三步:

    game = Game(seed=1)
    while not game.is_over:
        action = 某个策略(game.observation(game.current), game.legal_actions())
        game.step(action)
    print(game.scores)

任何时刻只有一个座位需要做决定(game.current)。换三张、定缺、对一张弃牌的响应
这些"同时决定"的环节被拆成逐个询问,先做的决定在全部做完之前对其他人不可见。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from . import actions as A
from .actions import Action, ActionType
from .config import RuleConfig
from .fan import FanResult, Meld, MeldType, WinContext, best_ting, evaluate_fan
from .hand import has_suit, is_win
from .tiles import (
    COPIES,
    NUM_RANKS,
    NUM_SUITS,
    NUM_TILE_TYPES,
    NUM_TILES,
    counts_to_tiles,
    full_wall,
)

NUM_SEATS = 4
HAND_SIZE = 13
_DEALT = NUM_SEATS * HAND_SIZE + 1  # 发牌用掉 53 张


class Phase(IntEnum):
    EXCHANGE = 0  # 换三张
    CHOOSE_VOID = 1  # 定缺
    TURN = 2  # 轮到某人: 出牌 / 暗杠 / 加杠 / 自摸
    RESPONSE = 3  # 对一张弃牌的响应: 胡 / 杠 / 碰 / 过
    ROB_KONG = 4  # 对加杠的响应: 抢杠胡 / 过
    END = 5


class IllegalAction(ValueError):
    pass


@dataclass(frozen=True)
class Transfer:
    """一笔分数流转。所有计分都走这里,所以四家总分恒为 0。"""

    kind: str  # "hu" | "gang" | "hua_zhu" | "da_jiao" | "tui_shui"
    payer: int
    payee: int
    amount: int
    note: str = ""


@dataclass(frozen=True)
class WinRecord:
    seat: int
    tile: Optional[int]  # 胡的那张牌;天胡时为 None
    zimo: bool
    from_seat: Optional[int]  # 点炮者;自摸时为 None
    fan: int
    capped_fan: int
    points: int  # 每位付分者付出的分数
    names: Tuple[str, ...]


class Game:
    def __init__(
        self,
        config: Optional[RuleConfig] = None,
        seed: Optional[int] = None,
        dealer: int = 0,
        wall: Optional[Sequence[int]] = None,
        exchange_direction: Optional[int] = None,
        record_events: bool = True,
    ) -> None:
        """开一局新牌。

        seed: 随机种子,决定洗牌和换牌方向;同一种子 + 同一动作序列 = 完全相同的一局。
        wall: 指定牌墙(108 张的排列),用于测试和复盘;给了就不再洗牌。
        exchange_direction: 换三张方向,1=给下家 2=给对家 3=给上家;不给则随机。
        record_events: 是否记录事件流(给界面用)。训练时关掉可以省时间。
        """
        if not 0 <= dealer < NUM_SEATS:
            raise ValueError(f"dealer 必须在 0..3: {dealer}")
        self.config = config or RuleConfig()
        self.seed = seed
        self.dealer = dealer
        rng = random.Random(seed)

        self.custom_wall = wall is not None
        if wall is None:
            wall_list = full_wall()
            rng.shuffle(wall_list)
        else:
            wall_list = list(wall)
            _validate_wall(wall_list)
        if exchange_direction is None:
            exchange_direction = rng.choice((1, 2, 3))
        elif exchange_direction not in (1, 2, 3):
            raise ValueError("exchange_direction 必须是 1、2 或 3")
        self.exchange_direction = exchange_direction

        self.wall: List[int] = wall_list
        self.wall_pos = _DEALT
        self.hands: List[List[int]] = [[0] * NUM_TILE_TYPES for _ in range(NUM_SEATS)]
        for seat in range(NUM_SEATS):
            for t in wall_list[seat * HAND_SIZE : (seat + 1) * HAND_SIZE]:
                self.hands[seat][t] += 1
        self.hands[dealer][wall_list[_DEALT - 1]] += 1

        self.melds: List[List[Meld]] = [[] for _ in range(NUM_SEATS)]
        self.discards: List[List[int]] = [[] for _ in range(NUM_SEATS)]
        self.void: List[int] = [-1] * NUM_SEATS
        self.won: List[bool] = [False] * NUM_SEATS
        self.wins: List[WinRecord] = []
        self.scores: List[int] = [0] * NUM_SEATS
        self.transfers: List[Transfer] = []
        self.discards_made: List[int] = [0] * NUM_SEATS
        self.any_meld = False  # 是否已有人碰/杠(影响天胡地胡)

        # 换三张
        self.exchange_out: List[List[int]] = [[] for _ in range(NUM_SEATS)]
        self.exchange_in: List[List[int]] = [[] for _ in range(NUM_SEATS)]
        self.exchange_done = False

        # 当前回合
        self.phase = Phase.TURN
        self.current = dealer
        self.drawn: Optional[int] = None
        self.can_declare = True  # 本回合能否胡/杠(碰牌之后只能出牌)
        self.after_gang = False  # 本回合的牌是否杠后补的

        # 等待响应的弃牌 / 加杠
        self.last_discard: Optional[int] = None
        self.last_discarder: Optional[int] = None
        self.discard_after_gang = False
        self.discard_is_last = False
        self.rob_tile: Optional[int] = None
        self.rob_from: Optional[int] = None
        self._pending: List[Tuple[int, List[Action]]] = []
        self._pending_idx = 0
        self._responses: Dict[int, Action] = {}

        self.end_reason: Optional[str] = None
        self.history: List[int] = []  # 动作编号序列,用于复盘
        self.record_events = record_events
        self.events: List[Dict[str, Any]] = []
        self._legal: List[Action] = []

        self._emit("deal", dealer=dealer)
        if self.config.exchange_three:
            self._ask_exchange(dealer)
        else:
            self.exchange_done = True
            self._ask_void(dealer)

    # ------------------------------------------------------------------ 查询

    @property
    def is_over(self) -> bool:
        return self.phase == Phase.END

    @property
    def wall_remaining(self) -> int:
        return len(self.wall) - self.wall_pos

    def legal_actions(self) -> List[Action]:
        """当前决策者(self.current)可以做的全部动作。"""
        return list(self._legal)

    def legal_action_ids(self) -> List[int]:
        return [a.id for a in self._legal]

    def hand_tiles(self, seat: int) -> List[int]:
        return counts_to_tiles(self.hands[seat])

    def active_seats(self) -> List[int]:
        """还没胡牌的座位。"""
        return [s for s in range(NUM_SEATS) if not self.won[s]]

    # ------------------------------------------------------------------ 推进

    def step(self, action: Union[Action, int]) -> None:
        """让当前决策者执行一个动作。非法动作抛出 IllegalAction,状态不变。"""
        if self.phase == Phase.END:
            raise IllegalAction("牌局已经结束")
        if not isinstance(action, Action):
            action = Action.from_id(int(action))
        if action not in self._legal:
            raise IllegalAction(
                f"座位 {self.current} 在 {self.phase.name} 阶段不能执行 {action}"
            )
        self.history.append(action.id)
        if self.phase == Phase.TURN:
            self._step_turn(action)
        elif self.phase == Phase.RESPONSE or self.phase == Phase.ROB_KONG:
            self._step_response(action)
        elif self.phase == Phase.EXCHANGE:
            self._step_exchange(action)
        else:
            self._step_void(action)

    # ------------------------------------------------------------------ 换三张

    def _ask_exchange(self, seat: int) -> None:
        self.phase = Phase.EXCHANGE
        self.current = seat
        hand = self.hands[seat]
        picked = self.exchange_out[seat]
        if picked:
            suit = picked[0] // NUM_RANKS
            tiles = [t for t in range(suit * NUM_RANKS, (suit + 1) * NUM_RANKS) if hand[t]]
        else:
            tiles = []
            for suit in range(NUM_SUITS):
                seg = range(suit * NUM_RANKS, (suit + 1) * NUM_RANKS)
                if sum(hand[t] for t in seg) >= 3:
                    tiles.extend(t for t in seg if hand[t])
        self._legal = [A.exchange(t) for t in tiles]

    def _step_exchange(self, action: Action) -> None:
        seat = self.current
        self.hands[seat][action.tile] -= 1
        self.exchange_out[seat].append(action.tile)
        if len(self.exchange_out[seat]) < 3:
            self._ask_exchange(seat)
            return
        nxt = (seat + 1) % NUM_SEATS
        if nxt != self.dealer:
            self._ask_exchange(nxt)
            return
        for src in range(NUM_SEATS):
            dst = (src + self.exchange_direction) % NUM_SEATS
            self.exchange_in[dst] = list(self.exchange_out[src])
            for t in self.exchange_out[src]:
                self.hands[dst][t] += 1
        self.exchange_done = True
        self._emit("exchange", direction=self.exchange_direction)
        self._ask_void(self.dealer)

    # ------------------------------------------------------------------ 定缺

    def _ask_void(self, seat: int) -> None:
        self.phase = Phase.CHOOSE_VOID
        self.current = seat
        self._legal = [A.choose_void(s) for s in range(NUM_SUITS)]

    def _step_void(self, action: Action) -> None:
        seat = self.current
        self.void[seat] = action.tile
        nxt = (seat + 1) % NUM_SEATS
        if nxt != self.dealer:
            self._ask_void(nxt)
            return
        self._emit("void", voids=list(self.void))
        self._start_turn(self.dealer, drawn=None)

    # ------------------------------------------------------------------ 回合

    def _start_turn(
        self,
        seat: int,
        drawn: Optional[int],
        can_declare: bool = True,
        after_gang: bool = False,
    ) -> None:
        self.phase = Phase.TURN
        self.current = seat
        self.drawn = drawn
        self.can_declare = can_declare
        self.after_gang = after_gang

        hand = self.hands[seat]
        void = self.void[seat]
        void_tiles = [t for t in range(void * NUM_RANKS, (void + 1) * NUM_RANKS) if hand[t]]
        legal: List[Action] = []
        if can_declare:
            if not void_tiles and is_win(hand, len(self.melds[seat])):
                legal.append(A.HU)
            if self.wall_remaining > 0:
                for t in range(NUM_TILE_TYPES):
                    if hand[t] == COPIES and t // NUM_RANKS != void:
                        legal.append(A.an_gang(t))
                for m in self.melds[seat]:
                    if m.type == MeldType.PONG and hand[m.tile]:
                        legal.append(A.jia_gang(m.tile))
        # 手里还有缺门牌时必须先打缺门
        tiles = void_tiles or [t for t in range(NUM_TILE_TYPES) if hand[t]]
        legal.extend(A.discard(t) for t in tiles)
        self._legal = legal

    def _step_turn(self, action: Action) -> None:
        seat = self.current
        hand = self.hands[seat]
        tile = action.tile
        kind = action.type

        if kind == ActionType.HU:
            self._win(
                seat,
                tile=self.drawn,
                zimo=True,
                from_seat=None,
                gang_shang_hua=self.after_gang,
                haidi=self.drawn is not None and self.wall_remaining == 0,
            )
            self._after_wins([seat], pivot=seat)

        elif kind == ActionType.AN_GANG:
            hand[tile] -= COPIES
            self.melds[seat].append(Meld(MeldType.AN_GANG, tile, seat))
            self.any_meld = True
            self._emit("gang", seat=seat, tile=tile, kind="AN_GANG", from_seat=seat)
            payers = [s for s in self.active_seats() if s != seat]
            self._pay_gang(seat, payers, self.config.an_gang_score, "暗杠")
            self._draw(seat, after_gang=True)

        elif kind == ActionType.JIA_GANG:
            hand[tile] -= 1
            pending = []
            for i in range(1, NUM_SEATS):
                s = (seat + i) % NUM_SEATS
                if not self.won[s] and self._can_win_with(s, tile):
                    pending.append((s, [A.HU, A.PASS]))
            if pending:
                self.rob_tile = tile
                self.rob_from = seat
                self._emit("gang_declared", seat=seat, tile=tile)
                self._ask_responses(Phase.ROB_KONG, pending)
            else:
                self._finish_jia_gang(seat, tile)

        else:  # DISCARD
            hand[tile] -= 1
            self.discards[seat].append(tile)
            self.discards_made[seat] += 1
            self.last_discard = tile
            self.last_discarder = seat
            self.discard_after_gang = self.after_gang
            self.discard_is_last = self.wall_remaining == 0
            self._emit("discard", seat=seat, tile=tile)

            pending = []
            for i in range(1, NUM_SEATS):
                s = (seat + i) % NUM_SEATS
                if self.won[s]:
                    continue
                options: List[Action] = []
                if self._can_win_with(s, tile):
                    options.append(A.HU)
                # 最后一张弃牌只能胡,不能碰杠;缺门的牌不能碰杠
                if not self.discard_is_last and tile // NUM_RANKS != self.void[s]:
                    have = self.hands[s][tile]
                    if have >= 2:
                        options.append(A.PONG)
                    if have == 3:
                        options.append(A.MING_GANG)
                if options:
                    options.append(A.PASS)
                    pending.append((s, options))
            if pending:
                self._ask_responses(Phase.RESPONSE, pending)
            else:
                self._draw(self._next_active(seat))

    def _finish_jia_gang(self, seat: int, tile: int) -> None:
        for m in self.melds[seat]:
            if m.type == MeldType.PONG and m.tile == tile:
                m.type = MeldType.JIA_GANG
                break
        self.any_meld = True
        self._emit("gang", seat=seat, tile=tile, kind="JIA_GANG", from_seat=seat)
        payers = [s for s in self.active_seats() if s != seat]
        self._pay_gang(seat, payers, self.config.jia_gang_score, "加杠")
        self._draw(seat, after_gang=True)

    # ------------------------------------------------------------------ 响应

    def _ask_responses(self, phase: Phase, pending: List[Tuple[int, List[Action]]]) -> None:
        self.phase = phase
        self._pending = pending
        self._pending_idx = 0
        self._responses = {}
        self.current, self._legal = pending[0]

    def _step_response(self, action: Action) -> None:
        self._responses[self.current] = action
        self._pending_idx += 1
        if self._pending_idx < len(self._pending):
            self.current, self._legal = self._pending[self._pending_idx]
            return
        if self.phase == Phase.RESPONSE:
            self._resolve_discard()
        else:
            self._resolve_rob_kong()

    def _resolve_discard(self) -> None:
        tile = self.last_discard
        discarder = self.last_discarder
        assert tile is not None and discarder is not None
        responses = self._responses

        # 胡优先于碰杠;多人同时胡 = 一炮多响,全部成立
        winners = [s for s, _ in self._pending if responses[s].type == ActionType.HU]
        if winners:
            for s in winners:
                self._win(
                    s,
                    tile=tile,
                    zimo=False,
                    from_seat=discarder,
                    gang_shang_pao=self.discard_after_gang,
                    haidi=self.discard_is_last,
                )
            self._after_wins(winners, pivot=discarder)
            return

        for s, _ in self._pending:
            kind = responses[s].type
            if kind == ActionType.MING_GANG:
                self.hands[s][tile] -= 3
                self.discards[discarder].pop()
                self.melds[s].append(Meld(MeldType.MING_GANG, tile, discarder))
                self.any_meld = True
                self._emit("gang", seat=s, tile=tile, kind="MING_GANG", from_seat=discarder)
                self._pay_gang(s, [discarder], self.config.ming_gang_score, "直杠")
                self._draw(s, after_gang=True)
                return
            if kind == ActionType.PONG:
                self.hands[s][tile] -= 2
                self.discards[discarder].pop()
                self.melds[s].append(Meld(MeldType.PONG, tile, discarder))
                self.any_meld = True
                self._emit("pong", seat=s, tile=tile, from_seat=discarder)
                self._start_turn(s, drawn=None, can_declare=False)
                return

        self._draw(self._next_active(discarder))

    def _resolve_rob_kong(self) -> None:
        tile = self.rob_tile
        konger = self.rob_from
        assert tile is not None and konger is not None
        winners = [s for s, _ in self._pending if self._responses[s].type == ActionType.HU]
        if not winners:
            self._finish_jia_gang(konger, tile)
            return
        # 被抢杠: 杠不成立,那张牌按点炮处理,留在杠牌者的弃牌区
        self.discards[konger].append(tile)
        for s in winners:
            self._win(s, tile=tile, zimo=False, from_seat=konger, qiang_gang=True)
        self._after_wins(winners, pivot=konger)

    # ------------------------------------------------------------------ 摸牌 / 胡牌 / 结束

    def _draw(self, seat: int, after_gang: bool = False) -> None:
        if self.wall_remaining == 0:
            self._end("wall_exhausted")
            return
        tile = self.wall[self.wall_pos]
        self.wall_pos += 1
        self.hands[seat][tile] += 1
        self._emit("draw", seat=seat, tile=tile, after_gang=after_gang)
        self._start_turn(seat, drawn=tile, after_gang=after_gang)

    def _next_active(self, seat: int) -> int:
        for i in range(1, NUM_SEATS + 1):
            s = (seat + i) % NUM_SEATS
            if not self.won[s]:
                return s
        raise RuntimeError("没有未胡的玩家")

    def _can_win_with(self, seat: int, tile: int) -> bool:
        """seat 能否胡别人打出(或加杠)的 tile。"""
        void = self.void[seat]
        hand = self.hands[seat]
        if tile // NUM_RANKS == void or has_suit(hand, void):
            return False
        hand[tile] += 1
        ok = is_win(hand, len(self.melds[seat]))
        hand[tile] -= 1
        return ok

    def _win(
        self,
        seat: int,
        tile: Optional[int],
        zimo: bool,
        from_seat: Optional[int],
        gang_shang_hua: bool = False,
        gang_shang_pao: bool = False,
        qiang_gang: bool = False,
        haidi: bool = False,
    ) -> None:
        cfg = self.config
        first_round = self.discards_made[seat] == 0 and not self.any_meld
        ctx = WinContext(
            zimo=zimo,
            tianhu=zimo and seat == self.dealer and first_round,
            dihu=seat != self.dealer and first_round,
            gang_shang_hua=gang_shang_hua,
            gang_shang_pao=gang_shang_pao,
            qiang_gang=qiang_gang,
            haidi=haidi,
        )
        counts = self.hands[seat]
        if not zimo:
            counts = list(counts)
            counts[tile] += 1
        result: FanResult = evaluate_fan(counts, self.melds[seat], ctx, cfg)

        if zimo:
            payers = [s for s in self.active_seats() if s != seat]
            per_payer = result.points + (cfg.base_score if cfg.zimo_mode == "jia_di" else 0)
        else:
            payers = [from_seat]
            per_payer = result.points
        self.won[seat] = True
        self.wins.append(
            WinRecord(
                seat=seat,
                tile=tile,
                zimo=zimo,
                from_seat=from_seat,
                fan=result.fan,
                capped_fan=result.capped_fan,
                points=per_payer,
                names=result.names,
            )
        )
        self._emit(
            "hu",
            seat=seat,
            tile=tile,
            zimo=zimo,
            from_seat=from_seat,
            fan=result.fan,
            points=per_payer,
            names=list(result.names),
        )
        note = "/".join(result.names)
        for p in payers:
            self._transfer("hu", p, seat, per_payer, note)

    def _after_wins(self, winners: List[int], pivot: int) -> None:
        if sum(self.won) >= NUM_SEATS - 1:
            self._end("three_won")
            return
        # 一炮多响时,从点炮者起数最远的那位胡牌者的下家继续摸牌
        last = max(winners, key=lambda s: (s - pivot) % NUM_SEATS)
        self._draw(self._next_active(last))

    def _end(self, reason: str) -> None:
        self.phase = Phase.END
        self.current = -1
        self._legal = []
        self.drawn = None
        self.end_reason = reason
        if reason == "wall_exhausted":
            self._settle_draw()
        self._emit("end", reason=reason, scores=list(self.scores))

    # ------------------------------------------------------------------ 计分

    def _transfer(self, kind: str, payer: int, payee: int, amount: int, note: str = "") -> None:
        if amount <= 0 or payer == payee:
            return
        self.scores[payer] -= amount
        self.scores[payee] += amount
        self.transfers.append(Transfer(kind, payer, payee, amount, note))
        self._emit("transfer", kind=kind, payer=payer, payee=payee, amount=amount, note=note)

    def _pay_gang(self, seat: int, payers: Sequence[int], unit: int, note: str) -> None:
        amount = unit * self.config.base_score
        for p in payers:
            self._transfer("gang", p, seat, amount, note)

    def _settle_draw(self) -> None:
        """流局结算: 查花猪、查大叫、退税。只涉及还没胡牌的玩家。"""
        cfg = self.config
        active = self.active_seats()
        hua_zhu = [s for s in active if has_suit(self.hands[s], self.void[s])]
        ting: Dict[int, Tuple[int, FanResult]] = {}
        for s in active:
            if s in hua_zhu:
                continue
            best = best_ting(self.hands[s], self.melds[s], self.void[s], cfg)
            if best is not None:
                ting[s] = best
        no_ting = [s for s in active if s not in hua_zhu and s not in ting]

        if cfg.cha_hua_zhu:
            cap_points = cfg.base_score * (1 << cfg.max_fan)
            for pig in hua_zhu:
                for s in active:
                    if s not in hua_zhu:
                        self._transfer("hua_zhu", pig, s, cap_points, "查花猪")

        if cfg.cha_da_jiao:
            for loser in no_ting:
                for s, (_, result) in ting.items():
                    self._transfer("da_jiao", loser, s, result.points, "/".join(result.names))

        if cfg.tui_shui:
            refunders = set(hua_zhu) | set(no_ting)
            for tr in list(self.transfers):
                if tr.kind == "gang" and tr.payee in refunders:
                    self._transfer("tui_shui", tr.payee, tr.payer, tr.amount, "退税")

    # ------------------------------------------------------------------ 事件与视图

    def _emit(self, type_: str, **data: Any) -> None:
        if self.record_events:
            data["type"] = type_
            self.events.append(data)

    def events_for(self, seat: int, start: int = 0) -> List[Dict[str, Any]]:
        """seat 能看到的事件流(别人摸的牌被隐去)。牌局结束后不再隐藏。"""
        out = []
        reveal = self.is_over
        for ev in self.events[start:]:
            if ev["type"] == "draw" and ev["seat"] != seat and not reveal:
                ev = dict(ev)
                ev["tile"] = None
            out.append(ev)
        return out

    def observation(self, seat: int) -> Dict[str, Any]:
        """seat 视角下的局面: 只包含该座位按规则能看到的信息。

        别人的手牌、别人暗杠的牌、别人还没公开的定缺和换牌都不会出现。
        牌局结束后多一个 "hands" 字段,公开所有人的手牌。
        """
        over = self.is_over
        voids_public = self.phase not in (Phase.EXCHANGE, Phase.CHOOSE_VOID)
        melds = []
        for s in range(NUM_SEATS):
            row = []
            for m in self.melds[s]:
                hidden = m.type == MeldType.AN_GANG and s != seat and not over
                row.append(
                    {
                        "type": m.type.name,
                        "tile": None if hidden else m.tile,
                        "from_seat": m.from_seat,
                    }
                )
            melds.append(row)

        pending_discard = None
        if self.phase == Phase.RESPONSE:
            pending_discard = {"seat": self.last_discarder, "tile": self.last_discard}
        elif self.phase == Phase.ROB_KONG:
            pending_discard = {"seat": self.rob_from, "tile": self.rob_tile, "rob_kong": True}

        my_turn = self.current == seat and not over
        obs: Dict[str, Any] = {
            "seat": seat,
            "phase": self.phase.name,
            "current": self.current,
            "dealer": self.dealer,
            "wall_remaining": self.wall_remaining,
            "hand": counts_to_tiles(self.hands[seat]),
            "drawn": self.drawn if my_turn and self.phase == Phase.TURN else None,
            "hand_sizes": [sum(h) for h in self.hands],
            "melds": melds,
            "discards": [list(d) for d in self.discards],
            "void": [
                self.void[s] if self.void[s] >= 0 and (voids_public or s == seat) else None
                for s in range(NUM_SEATS)
            ],
            "won": list(self.won),
            "wins": [
                {
                    "seat": w.seat,
                    "tile": w.tile,
                    "zimo": w.zimo,
                    "from_seat": w.from_seat,
                    "fan": w.fan,
                    "points": w.points,
                    "names": list(w.names),
                }
                for w in self.wins
            ],
            "scores": list(self.scores),
            "pending_discard": pending_discard,
            # 自己回合: 这张牌是杠后补的;响应弃牌: 这张弃牌是杠后打出的。全桌都看得到
            "after_gang": (
                self.after_gang
                if self.phase == Phase.TURN
                else self.discard_after_gang if self.phase == Phase.RESPONSE else False
            ),
            "exchange": {
                "given": list(self.exchange_out[seat]),
                "received": list(self.exchange_in[seat]) if self.exchange_done else [],
                "direction": self.exchange_direction if self.exchange_done else None,
            },
            "legal_actions": [a.id for a in self._legal] if my_turn else [],
        }
        if over:
            obs["hands"] = [counts_to_tiles(h) for h in self.hands]
            obs["end_reason"] = self.end_reason
        return obs

    def result(self) -> Dict[str, Any]:
        """牌局结束后的完整结算。"""
        if not self.is_over:
            raise RuntimeError("牌局还没结束")
        return {
            "end_reason": self.end_reason,
            "scores": list(self.scores),
            "wins": list(self.wins),
            "transfers": list(self.transfers),
            "hands": [counts_to_tiles(h) for h in self.hands],
            "melds": [list(m) for m in self.melds],
            "void": list(self.void),
        }


def _validate_wall(wall: Sequence[int]) -> None:
    if len(wall) != NUM_TILES:
        raise ValueError(f"牌墙必须是 {NUM_TILES} 张,实际 {len(wall)} 张")
    counts = [0] * NUM_TILE_TYPES
    for t in wall:
        if not 0 <= t < NUM_TILE_TYPES:
            raise ValueError(f"牌墙里有非法的牌: {t}")
        counts[t] += 1
    if any(n != COPIES for n in counts):
        raise ValueError("牌墙里每种牌必须恰好 4 张")

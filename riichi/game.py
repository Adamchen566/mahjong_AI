"""对局状态机: 一个 Game 是一整场(默认半庄)。

规则见 docs/riichi-rules.md。引擎不打印、不读输入、不联网;随机性只来自种子。
任何时刻只有一个座位在做决定:

    game = Game(seed=1)
    while not game.is_over:
        seat = game.current
        action = policy(game.observation(seat), game.legal_actions())
        game.step(action)
"""
from __future__ import annotations

import random
from enum import IntEnum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import actions as A
from .actions import Action, ActionType
from .config import RuleConfig
from .hand import PON, decompose, is_agari, is_kokushi, waits
from .shanten import shanten
from .scoring import HandValue, Meld, MeldType, WinContext, evaluate, ron_points, tsumo_points
from .tiles import (
    FIVE_KINDS,
    NUM_KINDS,
    NUM_TILES,
    YAOCHU_SET,
    dora_of,
    full_wall,
    hand_tiles,
    kind_of,
)

NUM_SEATS = 4
DEAL_SIZE = 13
DEAD_WALL = 14
LIVE_END = NUM_TILES - DEAD_WALL  # 122: 可摸的牌到这里为止(每开一次杠再少一张)
MAX_KANS = 4


class Phase(IntEnum):
    TURN = 0  # 轮到的人: 出牌、立直、自摸、暗杠、加杠、九种九牌
    RIICHI = 1  # 刚宣言立直,选打哪张
    RESPONSE = 2  # 对弃牌的响应: 荣和、碰、大明杠、吃、过
    ROB_KAN = 3  # 抢杠: 荣和、过
    END = 4


class IllegalAction(Exception):
    pass


class Game:
    def __init__(
        self,
        config: Optional[RuleConfig] = None,
        seed: Optional[int] = None,
        walls: Optional[Sequence[Sequence[int]]] = None,
        record_events: bool = True,
    ) -> None:
        """一场对局。

        seed: 随机种子,决定每一局的洗牌。
        walls: 依次指定每一局的 136 张牌墙(排法见 docs/riichi-rules.md 第 7 节);
               用完之后的局由种子洗牌。
        record_events: 是否记录事件流,训练时可以关掉。
        """
        self.config = config or RuleConfig()
        self.seed = seed
        self.rng = random.Random(seed)
        self.custom_walls = [list(w) for w in walls] if walls else []
        self.walls_used: List[List[int]] = []
        self.record_events = record_events

        self.scores = [self.config.start_points] * NUM_SEATS
        self.round_wind = 0  # 0 东场、1 南场、2 西场 ...
        self.kyoku = 0  # 0..3,这个场风里的第几局
        self.dealer = 0
        self.honba = 0
        self.sticks = 0  # 供托的立直棒
        self.hand_index = -1
        self.history: List[int] = []
        self.events: List[Dict[str, Any]] = []
        self.hand_results: List[Dict[str, Any]] = []
        self.end_reason: Optional[str] = None
        self.phase = Phase.TURN
        self.current = -1
        self._legal_cache: Optional[List[Action]] = None
        self._hand_event_start = 0
        self._start_hand()

    # ------------------------------------------------------------------ 基本属性

    @property
    def is_over(self) -> bool:
        return self.phase == Phase.END

    @property
    def wall_remaining(self) -> int:
        """还能摸的牌数(不含王牌)。"""
        return LIVE_END - self.draw_pos - self.kan_total

    @property
    def last_round(self) -> int:
        """正常情况下的最后一个场风。"""
        return 1 if self.config.length == "hanchan" else 0

    def seat_wind(self, seat: int) -> int:
        return (seat - self.dealer) % NUM_SEATS

    def dora_indicators(self) -> List[int]:
        return [self.wall[130 - 2 * i] for i in range(self.dora_revealed)]

    def ura_indicators(self) -> List[int]:
        return [self.wall[131 - 2 * i] for i in range(self.dora_revealed)]

    def hand_tiles(self, seat: int) -> List[int]:
        return hand_tiles(self.hands[seat], self.reds[seat])

    def is_menzen(self, seat: int) -> bool:
        return all(m.type == MeldType.ANKAN for m in self.melds[seat])

    def ranks(self) -> List[int]:
        """每个座位的名次(0 = 第一名)。同分时座位号小的在前。"""
        order = sorted(range(NUM_SEATS), key=lambda s: (-self.scores[s], s))
        out = [0] * NUM_SEATS
        for r, s in enumerate(order):
            out[s] = r
        return out

    # ------------------------------------------------------------------ 开局

    def _next_wall(self) -> List[int]:
        if self.hand_index < len(self.custom_walls):
            wall = list(self.custom_walls[self.hand_index])
            if len(wall) != NUM_TILES:
                raise ValueError(f"牌墙必须是 {NUM_TILES} 张,给了 {len(wall)} 张")
        else:
            wall = full_wall(self.config.aka)
            self.rng.shuffle(wall)
        self.walls_used.append(wall)
        return wall

    def _start_hand(self) -> None:
        self.hand_index += 1
        self.wall = self._next_wall()
        self.draw_pos = DEAL_SIZE * NUM_SEATS
        self.kan_total = 0
        self.kans_by = [0] * NUM_SEATS
        self.dora_revealed = 1
        self.pending_dora = 0
        self.hands: List[List[int]] = []
        self.reds: List[List[int]] = []
        for s in range(NUM_SEATS):
            counts = [0] * NUM_KINDS
            reds = [0, 0, 0]
            for t in self.wall[s * DEAL_SIZE : (s + 1) * DEAL_SIZE]:
                counts[kind_of(t)] += 1
                if t >= 34:
                    reds[t - 34] += 1
            self.hands.append(counts)
            self.reds.append(reds)
        self.melds: List[List[Meld]] = [[] for _ in range(NUM_SEATS)]
        self.discards: List[List[int]] = [[] for _ in range(NUM_SEATS)]
        # 每张弃牌: [是否摸切, 是否立直宣言牌, 是否被吃碰杠走]
        self.discard_flags: List[List[List[bool]]] = [[] for _ in range(NUM_SEATS)]
        self.discard_kinds: List[Set[int]] = [set() for _ in range(NUM_SEATS)]
        self.discards_made = [0] * NUM_SEATS
        self.riichi = [0] * NUM_SEATS  # 0 没立直,1 立直,2 双立直
        self.riichi_pending = -1  # 宣言了、宣言牌还没通过的座位
        self.riichi_double = False
        self.ippatsu = [False] * NUM_SEATS
        self.temp_furiten = [False] * NUM_SEATS
        self.riichi_furiten = [False] * NUM_SEATS
        self.nagashi_ok = [True] * NUM_SEATS
        self.pao: List[Dict[str, int]] = [{} for _ in range(NUM_SEATS)]
        self.no_calls = True  # 这一局到现在还没有任何吃碰杠
        self.drawn: Optional[int] = None  # 当前回合刚摸的牌;吃碰之后为 None
        self.after_kan = False  # 当前回合的牌是岭上牌
        self.kuikae: Tuple[int, ...] = ()
        self.pending: Optional[Tuple[int, int, str]] = None  # (谁, 哪张牌, discard/kakan/ankan)
        self.resp_options: Dict[int, List[Action]] = {}
        self.resp_queue: List[int] = []
        self.responses: Dict[int, Action] = {}
        self.ron_waiters: List[int] = []
        self._hand_event_start = len(self.events)
        self._emit(
            "hand_start",
            round_wind=self.round_wind,
            kyoku=self.kyoku,
            honba=self.honba,
            sticks=self.sticks,
            dealer=self.dealer,
            dora_indicator=self.wall[130],
            scores=list(self.scores),
        )
        self._draw_turn(self.dealer)

    # ------------------------------------------------------------------ 事件

    def _emit(self, type_: str, **fields: Any) -> None:
        if self.record_events:
            fields["type"] = type_
            self.events.append(fields)

    def events_for(self, seat: int) -> List[Dict[str, Any]]:
        """某个座位能看到的事件流: 当前这一局里别人摸到的牌被隐去。"""
        out = []
        for i, ev in enumerate(self.events):
            if (
                ev["type"] == "draw"
                and ev["seat"] != seat
                and i >= self._hand_event_start
                and not self.is_over
            ):
                ev = dict(ev, tile=None)
            out.append(ev)
        return out

    # ------------------------------------------------------------------ 合法动作

    def legal_actions(self) -> List[Action]:
        if self._legal_cache is None:
            self._legal_cache = self._compute_legal()
        return list(self._legal_cache)

    def legal_action_ids(self) -> List[int]:
        return [a.id for a in self.legal_actions()]

    def _compute_legal(self) -> List[Action]:
        if self.phase == Phase.END:
            return []
        if self.phase in (Phase.RESPONSE, Phase.ROB_KAN):
            return list(self.resp_options[self.current])
        s = self.current
        if self.phase == Phase.RIICHI:
            return [A.discard(t) for t in self._riichi_discards(s)]
        counts = self.hands[s]
        out: List[Action] = []
        drew = self.drawn is not None
        kan_ok = drew and self.kan_total < MAX_KANS and self.wall_remaining >= 1
        if self.riichi[s]:
            out.append(A.discard(self.drawn))
            k = kind_of(self.drawn)
            if kan_ok and counts[k] == 4 and self._riichi_ankan_ok(s, k):
                out.append(A.ankan(k))
        else:
            reds = self.reds[s]
            forbidden = self.kuikae
            for k in range(NUM_KINDS):
                n = counts[k]
                if not n or k in forbidden:
                    continue
                if k in FIVE_KINDS and reds[k // 9]:
                    if n > reds[k // 9]:
                        out.append(A.discard(k))
                    out.append(A.discard(34 + k // 9))
                else:
                    out.append(A.discard(k))
            if kan_ok:
                for k in range(NUM_KINDS):
                    if counts[k] == 4:
                        out.append(A.ankan(k))
                for m in self.melds[s]:
                    if m.type == MeldType.PON and counts[m.kind]:
                        out.append(A.kakan(m.kind))
            if (
                drew
                and self.is_menzen(s)
                and self.scores[s] >= 1000
                and self.wall_remaining >= 4
                and self._riichi_discards(s)
            ):
                out.append(A.RIICHI)
        if drew and self._tsumo_value(s) is not None:
            out.append(A.TSUMO)
        if (
            drew
            and self.config.abortive_draws
            and self.no_calls
            and self.discards_made[s] == 0
            and sum(1 for k in YAOCHU_SET if counts[k]) >= 9
        ):
            out.append(A.KYUUSHU)
        out.sort(key=lambda a: a.id)
        return out

    def _own_counts(self, seat: int) -> List[int]:
        """手牌加自己副露里的牌,按种类计数。"""
        own = list(self.hands[seat])
        for m in self.melds[seat]:
            for t in m.tiles:
                own[kind_of(t)] += 1
        return own

    def _tenpai_waits(self, seat: int, counts: Optional[Sequence[int]] = None) -> Tuple[int, ...]:
        """听的牌;只听自己已经占满 4 张的牌不算听牌(返回空)。"""
        c = self.hands[seat] if counts is None else counts
        w = waits(c, len(self.melds[seat]))
        if not w:
            return ()
        own = list(c)
        for m in self.melds[seat]:
            for t in m.tiles:
                own[kind_of(t)] += 1
        if all(own[k] >= 4 for k in w):
            return ()
        return w

    def is_tenpai(self, seat: int) -> bool:
        return bool(self._tenpai_waits(seat))

    def _riichi_discards(self, seat: int) -> List[int]:
        """打出后仍然听牌的那些牌(具体的牌,含赤)。"""
        counts = self.hands[seat]
        reds = self.reds[seat]
        out: List[int] = []
        if shanten(counts, len(self.melds[seat])) > 0:  # 预筛: 打哪张都不可能听牌
            return out
        for k in range(NUM_KINDS):
            n = counts[k]
            if not n:
                continue
            counts[k] -= 1
            ok = bool(self._tenpai_waits(seat))
            counts[k] += 1
            if not ok:
                continue
            if k in FIVE_KINDS and reds[k // 9]:
                if n > reds[k // 9]:
                    out.append(k)
                out.append(34 + k // 9)
            else:
                out.append(k)
        return out

    def _riichi_ankan_ok(self, seat: int, k: int) -> bool:
        """立直后的暗杠: 听的牌不变,并且这四张在任何拆法里都只能是刻子。"""
        counts = self.hands[seat]
        n = len(self.melds[seat])
        c13 = list(counts)
        c13[k] -= 1
        before = waits(c13, n)
        c10 = list(counts)
        c10[k] = 0
        after = waits(c10, n + 1)
        if not before or set(before) != set(after):
            return False
        for w in before:
            c13[w] += 1
            decs = decompose(c13)
            c13[w] -= 1
            if not decs:
                return False
            for _, sets in decs:
                if (PON, k) not in sets:
                    return False
        return True

    def _is_furiten(self, seat: int) -> bool:
        if self.temp_furiten[seat] or self.riichi_furiten[seat]:
            return True
        own = self.discard_kinds[seat]
        return any(k in own for k in waits(self.hands[seat], len(self.melds[seat])))

    # ------------------------------------------------------------------ 和牌的价值

    def _win_value(
        self, seat: int, tile: int, tsumo: bool, chankan: bool = False, houtei: bool = False
    ) -> Optional[HandValue]:
        c, k, ctx = self._win_context(seat, tile, tsumo, chankan, houtei)
        return evaluate(c, self.melds[seat], k, ctx, self.config)

    def _win_context(
        self, seat: int, tile: int, tsumo: bool, chankan: bool = False, houtei: bool = False
    ) -> Tuple[List[int], int, WinContext]:
        """和牌时的 (含和牌的手牌计数, 和牌种类, 场况)。测试里也用它和独立算分库对照。"""
        counts = self.hands[seat]
        k = kind_of(tile)
        if tsumo:
            c = counts
        else:
            c = list(counts)
            c[k] += 1
        first = self.no_calls and self.discards_made[seat] == 0
        ctx = WinContext(
            tsumo=tsumo,
            riichi=self.riichi[seat],
            ippatsu=self.ippatsu[seat],
            rinshan=tsumo and self.after_kan,
            chankan=chankan,
            haitei=tsumo and not self.after_kan and self.wall_remaining == 0,
            houtei=houtei,
            tenhou=tsumo and first and seat == self.dealer and not self.after_kan,
            chiihou=tsumo and first and seat != self.dealer and not self.after_kan,
            seat_wind=self.seat_wind(seat),
            round_wind=self.round_wind % 4,
        )
        total = list(c)
        aka = sum(self.reds[seat]) + (1 if (not tsumo and tile >= 34) else 0)
        for m in self.melds[seat]:
            for t in m.tiles:
                total[kind_of(t)] += 1
                if t >= 34:
                    aka += 1
        ctx.aka = aka
        ctx.dora = sum(total[dora_of(kind_of(i))] for i in self.dora_indicators())
        if self.riichi[seat]:
            ctx.ura = sum(total[dora_of(kind_of(i))] for i in self.ura_indicators())
        return list(c), k, ctx

    def _tsumo_value(self, seat: int) -> Optional[HandValue]:
        if self.drawn is None or not is_agari(self.hands[seat], len(self.melds[seat])):
            return None
        return self._win_value(seat, self.drawn, tsumo=True)

    # ------------------------------------------------------------------ 推进

    def step(self, action: "Action | int") -> None:
        """执行一个动作。非法动作抛 IllegalAction,状态不变。"""
        if isinstance(action, int) and not isinstance(action, Action):
            if not 0 <= action < A.NUM_ACTIONS:
                raise IllegalAction(f"动作编号越界: {action}")
            action = Action.from_id(action)
        if self.phase == Phase.END:
            raise IllegalAction("对局已经结束")
        if action not in self.legal_actions():
            raise IllegalAction(f"座位 {self.current} 现在不能 {action}")
        self.history.append(action.id)
        self._legal_cache = None
        if self.phase in (Phase.RESPONSE, Phase.ROB_KAN):
            self._step_response(action)
            return
        s = self.current
        t = action.type
        if t == ActionType.DISCARD:
            self._do_discard(s, action.arg)
        elif t == ActionType.RIICHI:
            self.phase = Phase.RIICHI
            self.riichi_pending = s
            self.riichi_double = self.no_calls and self.discards_made[s] == 0
            self._emit("riichi", seat=s)
        elif t == ActionType.TSUMO:
            self._wins([s], tsumo=True, loser=-1, tile=self.drawn)
        elif t == ActionType.ANKAN:
            self._declare_ankan(s, action.arg)
        elif t == ActionType.KAKAN:
            self._declare_kakan(s, action.arg)
        elif t == ActionType.KYUUSHU:
            self._abort("kyuushu")
        else:  # pragma: no cover - legal_actions 不会给出别的
            raise IllegalAction(str(action))

    def _draw_turn(self, seat: int, rinshan: bool = False) -> None:
        if rinshan:
            tile = self.wall[NUM_TILES - self.kan_total]  # kan_total 已经加过 1
        else:
            tile = self.wall[self.draw_pos]
            self.draw_pos += 1
        self.hands[seat][kind_of(tile)] += 1
        if tile >= 34:
            self.reds[seat][tile - 34] += 1
        self.drawn = tile
        self.after_kan = rinshan
        self.kuikae = ()
        self.current = seat
        self.phase = Phase.TURN
        self._emit("draw", seat=seat, tile=tile, rinshan=rinshan)

    def _remove(self, seat: int, tile: int) -> None:
        self.hands[seat][kind_of(tile)] -= 1
        if tile >= 34:
            self.reds[seat][tile - 34] -= 1

    def _reveal_dora(self, n: int) -> None:
        for _ in range(n):
            self.dora_revealed += 1
            self._emit("dora", indicator=self.wall[130 - 2 * (self.dora_revealed - 1)])

    def _do_discard(self, s: int, tile: int) -> None:
        riichi_decl = self.phase == Phase.RIICHI
        tsumogiri = self.drawn == tile
        self._remove(s, tile)
        self.discards[s].append(tile)
        self.discard_flags[s].append([tsumogiri, riichi_decl, False])
        self.discard_kinds[s].add(kind_of(tile))
        self.discards_made[s] += 1
        self.temp_furiten[s] = False
        self.ippatsu[s] = False
        self.drawn = None
        self.after_kan = False
        self.kuikae = ()
        self._emit("discard", seat=s, tile=tile, tsumogiri=tsumogiri, riichi=riichi_decl)
        if self.pending_dora:
            n, self.pending_dora = self.pending_dora, 0
            self._reveal_dora(n)
        self._open_response(s, tile)

    # ------------------------------------------------------------------ 对弃牌的响应

    def _abort_pending(self) -> bool:
        """这张弃牌如果没人和,会不会直接途中流局(这时不问吃碰杠)。"""
        if not self.config.abortive_draws:
            return False
        if self.riichi_pending >= 0 and sum(1 for r in self.riichi if r) == 3:
            return True
        if self.kan_total == MAX_KANS and max(self.kans_by) < MAX_KANS:
            return True
        return self._suufon()

    def _suufon(self) -> bool:
        if not self.no_calls or self.discards_made != [1, 1, 1, 1]:
            return False
        first = kind_of(self.discards[0][0])
        return 27 <= first <= 30 and all(kind_of(self.discards[s][0]) == first for s in range(1, 4))

    def _open_response(self, s: int, tile: int) -> None:
        k = kind_of(tile)
        last = self.wall_remaining == 0
        no_calls = last or self._abort_pending()
        self.pending = (s, tile, "discard")
        self.resp_options = {}
        self.responses = {}
        self.ron_waiters = []
        queue: List[int] = []
        for i in range(1, NUM_SEATS):
            p = (s + i) % NUM_SEATS
            acts: List[Action] = []
            if k in waits(self.hands[p], len(self.melds[p])):
                self.ron_waiters.append(p)
                if not self._is_furiten(p) and self._win_value(p, tile, False, houtei=last) is not None:
                    acts.append(A.RON)
            if not no_calls and not self.riichi[p]:
                acts.extend(self._call_options(p, s, k))
            if acts:
                acts.append(A.PASS)
                acts.sort(key=lambda a: a.id)
                self.resp_options[p] = acts
                queue.append(p)
        self.resp_queue = queue
        if queue:
            self.phase = Phase.RESPONSE
            self.current = queue[0]
        else:
            self._resolve_discard()

    def _call_options(self, p: int, s: int, k: int) -> List[Action]:
        counts = self.hands[p]
        reds = self.reds[p]
        out: List[Action] = []
        n = counts[k]
        if n >= 2 and sum(counts) - n > 0:  # 碰完还得有别的牌可打(喰替)
            r = reds[k // 9] if k in FIVE_KINDS else 0
            if n - r >= 2:
                out.append(A.pon(False))
            if r:
                out.append(A.pon(True))
        if n == 3 and self.kan_total < MAX_KANS and self.wall_remaining >= 1:
            out.append(A.DAIMINKAN)
        if p == (s + 1) % NUM_SEATS and k < 27:
            r9 = k % 9
            for shape, (a, b, lo, hi) in enumerate(((k + 1, k + 2, 0, 6), (k - 1, k + 1, 1, 7), (k - 2, k - 1, 2, 8))):
                if not (lo <= r9 <= hi) or not counts[a] or not counts[b]:
                    continue
                forbidden = self._chi_kuikae(k, shape)
                counts[a] -= 1
                counts[b] -= 1
                can_discard = any(counts[j] and j not in forbidden for j in range(NUM_KINDS))
                counts[a] += 1
                counts[b] += 1
                if not can_discard:
                    continue
                five = a if a in FIVE_KINDS else (b if b in FIVE_KINDS else -1)
                if five < 0:
                    out.append(A.chi(shape, False))
                else:
                    r = reds[five // 9]
                    if counts[five] - r >= 1:
                        out.append(A.chi(shape, False))
                    if r:
                        out.append(A.chi(shape, True))
        return out

    @staticmethod
    def _chi_kuikae(k: int, shape: int) -> Tuple[int, ...]:
        """吃了之后不能打的牌: 現物,以及两面搭子另一头的筋。"""
        if shape == 0 and k % 9 <= 5:
            return (k, k + 3)
        if shape == 2 and k % 9 >= 3:
            return (k, k - 3)
        return (k,)

    def _step_response(self, action: Action) -> None:
        p = self.current
        self.responses[p] = action
        self.resp_queue.pop(0)
        if self.resp_queue:
            self.current = self.resp_queue[0]
            return
        if self.phase == Phase.ROB_KAN:
            self._resolve_rob()
        else:
            self._resolve_discard()

    def _mark_missed(self) -> None:
        """听这张牌而没和的人进入振听。"""
        for p in self.ron_waiters:
            self.temp_furiten[p] = True
            if self.riichi[p]:
                self.riichi_furiten[p] = True

    def _resolve_discard(self) -> None:
        s, tile, _ = self.pending
        last = self.wall_remaining == 0
        order = [(s + i) % NUM_SEATS for i in range(1, NUM_SEATS)]
        winners = [p for p in order if self.responses.get(p) == A.RON]
        if len(winners) == 3 and self.config.abortive_draws:
            self._abort("sanchahou")
            return
        if winners:
            self._wins(winners, tsumo=False, loser=s, tile=tile, houtei=last)
            return
        self._mark_missed()
        if self.riichi_pending >= 0:
            r = self.riichi_pending
            self.riichi_pending = -1
            self.riichi[r] = 2 if self.riichi_double else 1
            self.ippatsu[r] = True
            self.scores[r] -= 1000
            self.sticks += 1
            self._emit("riichi_accepted", seat=r, double=self.riichi_double, scores=list(self.scores))
        if self.config.abortive_draws:
            if all(self.riichi):
                self._abort("suucha_riichi")
                return
            if self._suufon():
                self._abort("suufon_renda")
                return
            if self.kan_total == MAX_KANS and max(self.kans_by) < MAX_KANS:
                self._abort("suukaikan")
                return
        self.pending = None
        caller = -1
        for p in order:
            a = self.responses.get(p)
            if a is not None and a.type in (ActionType.PON, ActionType.DAIMINKAN):
                caller = p
                break
        if caller < 0:
            for p in order:
                a = self.responses.get(p)
                if a is not None and a.type == ActionType.CHI:
                    caller = p
                    break
        if caller >= 0:
            self._do_call(caller, s, tile, self.responses[caller])
        elif last:
            self._exhaustive_draw()
        else:
            self._draw_turn((s + 1) % NUM_SEATS)

    def _do_call(self, p: int, s: int, tile: int, action: Action) -> None:
        k = kind_of(tile)
        self.discard_flags[s][-1][2] = True
        self.nagashi_ok[s] = False
        self.no_calls = False
        self.ippatsu = [False] * NUM_SEATS
        red = 34 + k // 9 if k < 27 else -1
        if action.type == ActionType.PON:
            used = [red, k] if action.arg else [k, k]
            for t in used:
                self._remove(p, t)
            self.melds[p].append(Meld(MeldType.PON, tuple([tile] + used), tile, s))
            self._check_pao(p, s, k)
            self._emit("pon", seat=p, from_seat=s, tile=tile, tiles=[tile] + used)
            self._after_call(p, (k,))
        elif action.type == ActionType.CHI:
            shape, use_red = divmod(action.arg, 2)
            kinds = ((k + 1, k + 2), (k - 1, k + 1), (k - 2, k - 1))[shape]
            used = [(34 + j // 9) if (use_red and j in FIVE_KINDS) else j for j in kinds]
            for t in used:
                self._remove(p, t)
            self.melds[p].append(Meld(MeldType.CHI, tuple([tile] + used), tile, s))
            self._emit("chi", seat=p, from_seat=s, tile=tile, tiles=[tile] + used)
            self._after_call(p, self._chi_kuikae(k, shape))
        else:  # 大明杠
            used = []
            if k in FIVE_KINDS and self.reds[p][k // 9]:
                used.append(red)
            used += [k] * (3 - len(used))
            for t in used:
                self._remove(p, t)
            self.melds[p].append(Meld(MeldType.DAIMINKAN, tuple([tile] + used), tile, s))
            self._check_pao(p, s, k)
            self._emit("kan", seat=p, kind="DAIMINKAN", from_seat=s, tile=tile, tiles=[tile] + used)
            self._after_kan(p, open_kan=True)

    def _after_call(self, p: int, kuikae: Tuple[int, ...]) -> None:
        self.current = p
        self.phase = Phase.TURN
        self.drawn = None
        self.after_kan = False
        self.kuikae = kuikae

    def _check_pao(self, p: int, s: int, k: int) -> None:
        if not self.config.pao or k < 27:
            return
        triplets = {m.kind for m in self.melds[p] if m.type != MeldType.CHI}
        if k >= 31 and all(d in triplets for d in (31, 32, 33)):
            self.pao[p]["大三元"] = s
        if k <= 30 and all(w in triplets for w in (27, 28, 29, 30)):
            self.pao[p]["大四喜"] = s

    # ------------------------------------------------------------------ 杠

    def _declare_ankan(self, s: int, k: int) -> None:
        tile = k
        robbers = []
        self.ron_waiters = []
        for i in range(1, NUM_SEATS):
            p = (s + i) % NUM_SEATS
            if self.melds[p] or k not in YAOCHU_SET:
                continue
            c = list(self.hands[p])
            c[k] += 1
            if is_kokushi(c):  # 暗杠只有国士无双能抢
                self.ron_waiters.append(p)
                if not self._is_furiten(p):
                    robbers.append(p)
        self.pending = (s, tile, "ankan")
        if robbers:
            self._open_rob(robbers)
        else:
            self._complete_kan()

    def _declare_kakan(self, s: int, k: int) -> None:
        tile = 34 + k // 9 if (k in FIVE_KINDS and self.reds[s][k // 9]) else k
        self._remove(s, tile)
        self._emit("kan_declared", seat=s, tile=tile)
        self.pending = (s, tile, "kakan")
        robbers = []
        self.ron_waiters = []
        for i in range(1, NUM_SEATS):
            p = (s + i) % NUM_SEATS
            if k in waits(self.hands[p], len(self.melds[p])):
                self.ron_waiters.append(p)
                if not self._is_furiten(p) and self._win_value(p, tile, False, chankan=True) is not None:
                    robbers.append(p)
        if robbers:
            self._open_rob(robbers)
        else:
            self._complete_kan()

    def _open_rob(self, robbers: List[int]) -> None:
        self.resp_options = {p: [A.RON, A.PASS] for p in robbers}
        self.resp_queue = list(robbers)
        self.responses = {}
        self.phase = Phase.ROB_KAN
        self.current = robbers[0]

    def _resolve_rob(self) -> None:
        s, tile, kind = self.pending
        order = [(s + i) % NUM_SEATS for i in range(1, NUM_SEATS)]
        winners = [p for p in order if self.responses.get(p) == A.RON]
        if len(winners) == 3 and self.config.abortive_draws:
            self._abort("sanchahou")
            return
        if winners:
            self._wins(winners, tsumo=False, loser=s, tile=tile, chankan=kind == "kakan")
            return
        self._complete_kan()

    def _complete_kan(self) -> None:
        s, tile, kind = self.pending
        self._mark_missed()
        self.pending = None
        k = kind_of(tile)
        if kind == "ankan":
            tiles = [t for t in self.hand_tiles(s) if kind_of(t) == k]
            self.hands[s][k] = 0
            if k in FIVE_KINDS:
                self.reds[s][k // 9] = 0
            self.melds[s].append(Meld(MeldType.ANKAN, tuple(tiles)))
            self._emit("kan", seat=s, kind="ANKAN", from_seat=-1, tile=tile, tiles=tiles)
            self._after_kan(s, open_kan=False)
        else:
            for i, m in enumerate(self.melds[s]):
                if m.type == MeldType.PON and m.kind == k:
                    self.melds[s][i] = Meld(MeldType.KAKAN, m.tiles + (tile,), m.called, m.from_seat)
                    self._emit(
                        "kan", seat=s, kind="KAKAN", from_seat=m.from_seat, tile=tile, tiles=list(m.tiles) + [tile]
                    )
                    break
            self._after_kan(s, open_kan=True)

    def _after_kan(self, s: int, open_kan: bool) -> None:
        self.kan_total += 1
        self.kans_by[s] += 1
        self.no_calls = False
        self.ippatsu = [False] * NUM_SEATS
        n, self.pending_dora = self.pending_dora, 0
        if open_kan:
            self._reveal_dora(n)  # 之前没翻的先翻出来
            self.pending_dora = 1  # 这一次的等出牌后再翻
        else:
            self._reveal_dora(n + 1)  # 暗杠立刻翻
        self._draw_turn(s, rinshan=True)

    # ------------------------------------------------------------------ 一局的结束

    def _payments(
        self, w: int, value: HandValue, tsumo: bool, loser: int, honba: int
    ) -> List[Tuple[int, int, int]]:
        """一次和牌的支付: [(付的人, 收的人, 点数)]。"""
        dealer_win = w == self.dealer
        base = value.base
        pao_seat, pao_base = -1, 0
        if self.config.pao and value.yakuman:
            for name in value.yakuman_names:
                if name in self.pao[w]:
                    pao_seat = self.pao[w][name]
                    pao_base += 8000
        pay: Dict[int, int] = {}
        others = [p for p in range(NUM_SEATS) if p != w]
        if tsumo:
            if pao_seat >= 0:
                pay[pao_seat] = ron_points(pao_base, dealer_win) + 300 * honba
                rest = base - pao_base
                if rest:
                    for p in others:
                        pay[p] = pay.get(p, 0) + tsumo_points(rest, dealer_win, p == self.dealer)
            else:
                for p in others:
                    pay[p] = tsumo_points(base, dealer_win, p == self.dealer) + 100 * honba
        else:
            total = ron_points(base, dealer_win)
            if pao_seat >= 0 and pao_seat != loser:
                half = ron_points(pao_base, dealer_win) // 2
                pay[pao_seat] = half
                pay[loser] = total - half + 300 * honba
            else:
                pay[loser] = total + 300 * honba
        return [(p, w, amount) for p, amount in pay.items()]

    def _wins(
        self,
        winners: List[int],
        tsumo: bool,
        loser: int,
        tile: int,
        chankan: bool = False,
        houtei: bool = False,
    ) -> None:
        before = list(self.scores)
        wins = []
        any_riichi = any(self.riichi[w] for w in winners)
        for i, w in enumerate(winners):
            value = self._win_value(w, tile, tsumo, chankan=chankan, houtei=houtei)
            assert value is not None
            transfers = self._payments(w, value, tsumo, loser, self.honba if i == 0 else 0)
            for payer, payee, amount in transfers:
                self.scores[payer] -= amount
                self.scores[payee] += amount
            sticks = 0
            if i == 0:  # 供托归头跳者
                sticks = self.sticks * 1000
                self.scores[w] += sticks
                self.sticks = 0
            wins.append(
                {
                    "seat": w,
                    "from_seat": loser,
                    "tsumo": tsumo,
                    "tile": tile,
                    "han": value.han,
                    "fu": value.fu,
                    "yaku": list(value.yaku),
                    "yakuman": value.yakuman,
                    "limit": value.limit,
                    "base": value.base,
                    "payments": transfers,
                    "sticks": sticks,
                    "gain": sum(a for _, _, a in transfers) + sticks,
                    "hand": self.hand_tiles(w),
                    "melds": [self._meld_view(m) for m in self.melds[w]],
                    "riichi": self.riichi[w],
                }
            )
        dealer_won = self.dealer in winners
        result = {
            "type": "win",
            "reason": "tsumo" if tsumo else "ron",
            "wins": wins,
            "dora_indicators": self.dora_indicators(),
            "ura_indicators": self.ura_indicators() if any_riichi else [],
        }
        self._finish_hand(result, before, renchan=dealer_won, next_honba=self.honba + 1 if dealer_won else 0)

    def _exhaustive_draw(self) -> None:
        before = list(self.scores)
        tenpai = [self.is_tenpai(s) for s in range(NUM_SEATS)]
        nagashi = []
        if self.config.nagashi_mangan:
            for s in range(NUM_SEATS):
                if (
                    self.nagashi_ok[s]
                    and self.discards[s]
                    and all(kind_of(t) in YAOCHU_SET for t in self.discards[s])
                ):
                    nagashi.append(s)
        payments: List[Tuple[int, int, int]] = []
        if nagashi:
            for w in nagashi:
                for p in range(NUM_SEATS):
                    if p != w:
                        payments.append((p, w, tsumo_points(2000, w == self.dealer, p == self.dealer)))
        else:
            yes = [s for s in range(NUM_SEATS) if tenpai[s]]
            no = [s for s in range(NUM_SEATS) if not tenpai[s]]
            if yes and no:
                for p in no:
                    for w in yes:
                        payments.append((p, w, 3000 // len(no) // len(yes)))
        for payer, payee, amount in payments:
            self.scores[payer] -= amount
            self.scores[payee] += amount
        result = {
            "type": "ryukyoku",
            "reason": "nagashi_mangan" if nagashi else "exhaustive",
            "tenpai": tenpai,
            "nagashi": nagashi,
            "payments": payments,
            "hands": [self.hand_tiles(s) if tenpai[s] else None for s in range(NUM_SEATS)],
        }
        self._finish_hand(result, before, renchan=tenpai[self.dealer], next_honba=self.honba + 1)

    def _abort(self, reason: str) -> None:
        result = {"type": "ryukyoku", "reason": reason, "tenpai": None, "nagashi": [], "payments": []}
        self._finish_hand(result, list(self.scores), renchan=True, next_honba=self.honba + 1)

    def _finish_hand(self, result: Dict[str, Any], before: List[int], renchan: bool, next_honba: int) -> None:
        result.update(
            round_wind=self.round_wind,
            kyoku=self.kyoku,
            honba=self.honba,
            dealer=self.dealer,
            deltas=[self.scores[s] - before[s] for s in range(NUM_SEATS)],
            scores=list(self.scores),
            renchan=renchan,
        )
        self.hand_results.append(result)
        self.pending = None
        self.resp_options = {}
        self.resp_queue = []
        self._emit("hand_end", result=result)

        cfg = self.config
        target = cfg.target_points
        top = max(range(NUM_SEATS), key=lambda s: (self.scores[s], -s))
        if cfg.length == "one":
            return self._end_game("one_hand")
        if cfg.tobi and min(self.scores) < 0:
            return self._end_game("tobi")
        overtime = self.round_wind > self.last_round
        final_kyoku = self.kyoku == 3 and self.round_wind >= self.last_round
        if overtime and self.scores[top] >= target:
            return self._end_game("overtime_target")
        if renchan:
            if final_kyoku and top == self.dealer and self.scores[top] >= target:
                return self._end_game("dealer_top")
        else:
            if final_kyoku:
                if overtime:
                    return self._end_game("overtime_over")
                if self.scores[top] >= target:
                    return self._end_game("finished")
            self.dealer = (self.dealer + 1) % NUM_SEATS
            self.kyoku += 1
            if self.kyoku == 4:
                self.kyoku = 0
                self.round_wind += 1
        self.honba = next_honba
        self._start_hand()

    def _end_game(self, reason: str) -> None:
        if self.sticks:  # 剩下的供托归第一名
            top = max(range(NUM_SEATS), key=lambda s: (self.scores[s], -s))
            self.scores[top] += self.sticks * 1000
            self.sticks = 0
        self.end_reason = reason
        self.phase = Phase.END
        self.current = -1
        self._legal_cache = None
        self._emit("game_end", reason=reason, scores=list(self.scores), ranks=self.ranks())

    # ------------------------------------------------------------------ 结果与视图

    def final_points(self) -> List[float]:
        """名次分: (点数 − 返点) / 1000 + 顺位马,第一名再加起始点和返点的差。"""
        cfg = self.config
        oka = (cfg.target_points - cfg.start_points) * NUM_SEATS / 1000
        ranks = self.ranks()
        out = []
        for s in range(NUM_SEATS):
            v = (self.scores[s] - cfg.target_points) / 1000 + cfg.uma[ranks[s]]
            if ranks[s] == 0:
                v += oka
            out.append(v)
        return out

    def result(self) -> Dict[str, Any]:
        return {
            "scores": list(self.scores),
            "ranks": self.ranks(),
            "final_points": self.final_points(),
            "end_reason": self.end_reason,
            "hands": len(self.hand_results),
            "hand_results": self.hand_results,
        }

    @staticmethod
    def _meld_view(m: Meld) -> Dict[str, Any]:
        return {"type": m.type.name, "tiles": list(m.tiles), "called": m.called, "from_seat": m.from_seat}

    def observation(self, seat: int) -> Dict[str, Any]:
        """某个座位按规则能看到的东西。"""
        mine = self.current == seat and not self.is_over
        pending = None
        if self.pending is not None and self.phase in (Phase.RESPONSE, Phase.ROB_KAN):
            pending = {"seat": self.pending[0], "tile": self.pending[1], "kind": self.pending[2]}
        return {
            "seat": seat,
            "phase": self.phase.name,
            "current": self.current,
            "round_wind": self.round_wind,
            "kyoku": self.kyoku,
            "honba": self.honba,
            "sticks": self.sticks,
            "dealer": self.dealer,
            "seat_wind": self.seat_wind(seat),
            "scores": list(self.scores),
            "wall_remaining": self.wall_remaining,
            "dora_indicators": self.dora_indicators(),
            "hand": self.hand_tiles(seat),
            "drawn": self.drawn if mine and self.phase in (Phase.TURN, Phase.RIICHI) else None,
            "hand_sizes": [sum(h) for h in self.hands],
            "melds": [[self._meld_view(m) for m in ms] for ms in self.melds],
            "discards": [list(d) for d in self.discards],
            "discard_flags": [[list(f) for f in fs] for fs in self.discard_flags],
            "riichi": list(self.riichi),
            "riichi_pending": self.riichi_pending,
            "ippatsu": list(self.ippatsu),
            "furiten": self._is_furiten(seat) if not self.is_over else False,
            "pending": pending,
            "kuikae": list(self.kuikae) if mine else [],
            "legal_actions": self.legal_action_ids() if mine else [],
            "last_result": self.hand_results[-1] if self.hand_results else None,
            "end_reason": self.end_reason,
        }

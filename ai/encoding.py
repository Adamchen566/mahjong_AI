"""把一个座位看到的局面编码成网络的输入(阶段 4b)。

输出是 uint8 数组,形状 (NUM_CHANNELS, 27): 27 对应 27 种牌,每个通道是一类信息。
座位一律用相对位置(0 自己、1 下家、2 对家、3 上家),所以同一个网络可以坐任何位置。

两个入口,结果必须完全一样(tests/test_encoding.py 逐个决策点对比):

    encode(game, seat)   训练用。直接读 Game 的内部状态,不经过 observation() 的字典,快
    encode_obs(obs)      对局软件用。只拿得到 observation(),所以不可能看到别人的手牌

通道里的数大多是 0/1;少数通道是小整数(牌墙剩余、手牌张数等),
喂给网络之前乘上 OBS_SCALE 缩到 0..1。

另有 encode_oracle(): 别人的手牌和牌墙里剩的牌。只给训练时的价值头用,策略头和上线的模型都不碰它。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from chuanma.actions import NUM_ACTIONS
from chuanma.fan import MeldType
from chuanma.game import NUM_SEATS, Game, Phase
from chuanma.tiles import NUM_RANKS, NUM_TILE_TYPES

N = NUM_TILE_TYPES  # 27

# ---------------------------------------------------------------- 通道表
# (名字, 通道数, 说明, 最大值)。顺序就是通道顺序,改动它等于换了一种输入格式,旧模型不能再用。
CHANNEL_GROUPS: Tuple[Tuple[str, int, str, int], ...] = (
    ("hand", 4, "自己的手牌: 第 k 个通道表示这种牌至少有 k 张", 1),
    ("drawn", 1, "刚摸的那张", 1),
    ("pong", 4, "四家的碰(按相对座位)", 1),
    ("gang", 4, "四家看得见的杠: 直杠、加杠、自己的暗杠", 1),
    ("discard", 16, "四家的弃牌,每家 4 个通道: 弃了至少 k 张", 1),
    ("last_discard", 4, "四家各自最近打出的一张", 1),
    ("unseen", 4, "没见过的张数: 第 k 个通道表示至少还有 k 张没露面", 1),
    ("void", 4, "四家的缺门: 缺的那门 9 个位置置 1(还没公开的不写)", 1),
    ("pending", 1, "等我响应的那张(别人刚打出的,或别人要加杠的)", 1),
    ("exchange_given", 1, "换三张时我换出去的牌(张数)", 3),
    ("exchange_received", 1, "换三张时我收到的牌(张数)", 3),
    # 以下是标量,整个通道填同一个数
    ("phase", 5, "阶段: 换三张、定缺、自己的回合、响应弃牌、抢杠", 1),
    ("won", 3, "下家、对家、上家是否已经胡牌离场", 1),
    ("dealer", 4, "庄家在哪个相对座位", 1),
    ("wall", 1, "牌墙剩余张数", 55),
    ("hand_size", 4, "四家手牌张数", 14),
    ("hidden_gang", 3, "下家、对家、上家各有几个暗杠(看不到是什么牌)", 4),
    ("after_gang", 1, "这张牌是杠后补的(杠上花),或这张弃牌是杠后打的(杠上炮)", 1),
    ("pending_from", 3, "等我响应的牌来自下家、对家还是上家", 1),
    ("exchange_direction", 3, "换三张的方向: 给下家、给对家、给上家", 1),
)

CHANNEL_OFFSET: Dict[str, int] = {}
_scale: List[float] = []
_c = 0
for _name, _n, _doc, _max in CHANNEL_GROUPS:
    CHANNEL_OFFSET[_name] = _c
    _c += _n
    _scale.extend([1.0 / _max] * _n)
NUM_CHANNELS = _c
OBS_SHAPE = (NUM_CHANNELS, N)
OBS_SCALE = np.asarray(_scale, dtype=np.float32)  # 形状 (NUM_CHANNELS,)

_HAND = CHANNEL_OFFSET["hand"] * N
_DRAWN = CHANNEL_OFFSET["drawn"] * N
_PONG = CHANNEL_OFFSET["pong"] * N
_GANG = CHANNEL_OFFSET["gang"] * N
_DISCARD = CHANNEL_OFFSET["discard"] * N
_LAST = CHANNEL_OFFSET["last_discard"] * N
_UNSEEN = CHANNEL_OFFSET["unseen"] * N
_VOID = CHANNEL_OFFSET["void"] * N
_PENDING = CHANNEL_OFFSET["pending"] * N
_GIVEN = CHANNEL_OFFSET["exchange_given"] * N
_RECEIVED = CHANNEL_OFFSET["exchange_received"] * N
_S_PHASE = CHANNEL_OFFSET["phase"]
_S_WON = CHANNEL_OFFSET["won"]
_S_DEALER = CHANNEL_OFFSET["dealer"]
_S_WALL = CHANNEL_OFFSET["wall"]
_S_HAND_SIZE = CHANNEL_OFFSET["hand_size"]
_S_HIDDEN = CHANNEL_OFFSET["hidden_gang"]
_S_AFTER_GANG = CHANNEL_OFFSET["after_gang"]
_S_FROM = CHANNEL_OFFSET["pending_from"]
_S_DIR = CHANNEL_OFFSET["exchange_direction"]

_SIZE = NUM_CHANNELS * N
_FILL = [bytes([v]) * N for v in range(64)]
_SUIT_ONES = b"\x01" * NUM_RANKS
_PONG_TYPE = int(MeldType.PONG)
_AN_GANG_TYPE = int(MeldType.AN_GANG)

# 价值头的额外输入: 三个对手的手牌(各 4 个通道) + 牌墙里剩的牌(4 个通道)
ORACLE_CHANNELS = 16
ORACLE_SHAPE = (ORACLE_CHANNELS, N)

MeldView = Tuple[int, Optional[int]]  # (MeldType 的整数值, 牌;看不到时为 None)


def _write(
    seat: int,
    phase: int,
    hand: Sequence[int],
    drawn: Optional[int],
    melds: Sequence[Sequence[MeldView]],
    discards: Sequence[Sequence[int]],
    voids: Sequence[Optional[int]],
    won: Sequence[bool],
    zimo_tiles: Sequence[int],
    dealer: int,
    wall: int,
    hand_sizes: Sequence[int],
    pending_tile: Optional[int],
    pending_from: Optional[int],
    rob_kong: bool,
    given: Sequence[int],
    received: Sequence[int],
    direction: Optional[int],
    after_gang: bool,
) -> np.ndarray:
    """两个入口共用的写入部分。参数都是绝对座位,这里统一转成相对座位。"""
    buf = bytearray(_SIZE)
    seen = list(hand)  # 每种牌我已经看到几张

    for t in range(N):
        n = hand[t]
        if n:
            i = _HAND + t
            for _ in range(n):
                buf[i] = 1
                i += N
    if drawn is not None:
        buf[_DRAWN + drawn] = 1

    for rel in range(NUM_SEATS):
        s = (seat + rel) % NUM_SEATS
        hidden = 0
        for kind, tile in melds[s]:
            if tile is None:
                hidden += 1
            elif kind == _PONG_TYPE:
                buf[_PONG + rel * N + tile] = 1
                seen[tile] += 3
            else:
                buf[_GANG + rel * N + tile] = 1
                seen[tile] += 4
        if hidden:
            c = (_S_HIDDEN + rel - 1) * N
            buf[c : c + N] = _FILL[hidden]

        pile = discards[s]
        if pile:
            base = _DISCARD + rel * 4 * N
            for t in pile:
                seen[t] += 1
                i = base + t
                while buf[i]:
                    i += N
                buf[i] = 1
            buf[_LAST + rel * N + pile[-1]] = 1

        v = voids[s]
        if v is not None and v >= 0:
            i = _VOID + rel * N + v * NUM_RANKS
            buf[i : i + NUM_RANKS] = _SUIT_ONES

        c = (_S_HAND_SIZE + rel) * N
        buf[c : c + N] = _FILL[hand_sizes[s]]
        if rel and won[s]:
            c = (_S_WON + rel - 1) * N
            buf[c : c + N] = _FILL[1]

    for t in zimo_tiles:
        seen[t] += 1
    if pending_tile is not None:
        buf[_PENDING + pending_tile] = 1
        if rob_kong:
            seen[pending_tile] += 1  # 要加杠的那张已经亮出来,但还不在任何牌堆里
        rel = (pending_from - seat) % NUM_SEATS
        if rel:
            c = (_S_FROM + rel - 1) * N
            buf[c : c + N] = _FILL[1]

    for t in range(N):
        i = _UNSEEN + t
        for _ in range(4 - seen[t]):
            buf[i] = 1
            i += N

    for t in given:
        buf[_GIVEN + t] += 1
    for t in received:
        buf[_RECEIVED + t] += 1
    if direction is not None:
        c = (_S_DIR + direction - 1) * N
        buf[c : c + N] = _FILL[1]

    c = (_S_PHASE + phase) * N
    buf[c : c + N] = _FILL[1]
    c = (_S_DEALER + (dealer - seat) % NUM_SEATS) * N
    buf[c : c + N] = _FILL[1]
    c = _S_WALL * N
    buf[c : c + N] = _FILL[wall]
    if after_gang:
        c = _S_AFTER_GANG * N
        buf[c : c + N] = _FILL[1]

    return np.frombuffer(buf, dtype=np.uint8).reshape(OBS_SHAPE)


def encode(game: Game, seat: int) -> np.ndarray:
    """seat 视角的编码,直接读 Game 的内部状态。隐藏规则和 Game.observation() 一致。"""
    phase = game.phase
    public = phase > Phase.CHOOSE_VOID  # 定缺全部做完之前,别人的缺门不公开
    my_turn = game.current == seat

    melds = [
        [(int(m.type), None if (m.type == _AN_GANG_TYPE and s != seat) else m.tile) for m in game.melds[s]]
        for s in range(NUM_SEATS)
    ]
    voids = [game.void[s] if (public or s == seat) else None for s in range(NUM_SEATS)]
    zimo_tiles = [w.tile for w in game.wins if w.zimo and w.tile is not None and w.seat != seat]

    pending_tile = pending_from = None
    rob_kong = False
    after_gang = False
    if phase == Phase.TURN:
        after_gang = game.after_gang
    elif phase == Phase.RESPONSE:
        pending_tile, pending_from = game.last_discard, game.last_discarder
        after_gang = game.discard_after_gang
    elif phase == Phase.ROB_KONG:
        pending_tile, pending_from, rob_kong = game.rob_tile, game.rob_from, True

    done = game.exchange_done
    return _write(
        seat=seat,
        phase=int(phase),
        hand=game.hands[seat],
        drawn=game.drawn if (my_turn and phase == Phase.TURN) else None,
        melds=melds,
        discards=game.discards,
        voids=voids,
        won=game.won,
        zimo_tiles=zimo_tiles,
        dealer=game.dealer,
        wall=game.wall_remaining,
        hand_sizes=[sum(h) for h in game.hands],
        pending_tile=pending_tile,
        pending_from=pending_from,
        rob_kong=rob_kong,
        given=game.exchange_out[seat],
        received=game.exchange_in[seat] if done else (),
        direction=game.exchange_direction if done else None,
        after_gang=after_gang,
    )


def encode_obs(obs: Dict[str, Any]) -> np.ndarray:
    """从 Game.observation() 的字典编码。结果和 encode(game, obs["seat"]) 相同。"""
    seat = obs["seat"]
    hand = [0] * N
    for t in obs["hand"]:
        hand[t] += 1
    melds = [[(int(MeldType[m["type"]]), m["tile"]) for m in row] for row in obs["melds"]]
    zimo_tiles = [
        w["tile"] for w in obs["wins"] if w["zimo"] and w["tile"] is not None and w["seat"] != seat
    ]
    pending = obs["pending_discard"]
    exchange = obs["exchange"]
    return _write(
        seat=seat,
        phase=int(Phase[obs["phase"]]),
        hand=hand,
        drawn=obs["drawn"],
        melds=melds,
        discards=obs["discards"],
        voids=obs["void"],
        won=obs["won"],
        zimo_tiles=zimo_tiles,
        dealer=obs["dealer"],
        wall=obs["wall_remaining"],
        hand_sizes=obs["hand_sizes"],
        pending_tile=pending["tile"] if pending else None,
        pending_from=pending["seat"] if pending else None,
        rob_kong=bool(pending and pending.get("rob_kong")),
        given=exchange["given"],
        received=exchange["received"],
        direction=exchange["direction"],
        after_gang=obs["after_gang"],
    )


def encode_oracle(game: Game, seat: int) -> np.ndarray:
    """seat 看不到的东西: 三个对手的手牌和牌墙里还剩的牌。形状 (16, 27)。

    只用于训练时的价值头(知道全场信息,估值更准,训练更稳)。
    任何会坐进牌局的东西都不能调用它。
    """
    buf = bytearray(ORACLE_CHANNELS * N)
    for rel in range(1, NUM_SEATS):
        hand = game.hands[(seat + rel) % NUM_SEATS]
        base = (rel - 1) * 4 * N
        for t in range(N):
            i = base + t
            for _ in range(hand[t]):
                buf[i] = 1
                i += N
    base = 12 * N
    for t in game.wall[game.wall_pos :]:
        i = base + t
        while buf[i]:
            i += N
        buf[i] = 1
    return np.frombuffer(buf, dtype=np.uint8).reshape(ORACLE_SHAPE)


def legal_mask(game: Game) -> np.ndarray:
    """当前决策者的合法动作掩码,形状 (115,),合法的位置为 True。"""
    mask = np.zeros(NUM_ACTIONS, dtype=np.bool_)
    mask[game.legal_action_ids()] = True
    return mask


def mask_from_ids(ids: Sequence[int]) -> np.ndarray:
    mask = np.zeros(NUM_ACTIONS, dtype=np.bool_)
    mask[list(ids)] = True
    return mask


def describe_channels() -> List[Tuple[int, int, str, str]]:
    """(起始通道, 通道数, 名字, 说明) 的列表,给文档和调试用。"""
    return [(CHANNEL_OFFSET[name], n, name, doc) for name, n, doc, _ in CHANNEL_GROUPS]

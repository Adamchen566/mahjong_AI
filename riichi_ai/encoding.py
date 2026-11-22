"""把一个座位看到的日麻局面编码成网络输入。

输出是 uint8 数组,形状 (NUM_CHANNELS, 34): 34 对应 34 种牌,每个通道是一类信息。
座位一律用相对位置(0 自己、1 下家、2 对家、3 上家),同一个网络可以坐任何位置。

两个入口,结果必须完全一样(tests/test_riichi_encoding.py 逐个决策点对比):

    encode(game, seat)   训练用。直接读 Game 的内部状态
    encode_obs(obs)      对局软件用。只用 observation() 的字典,所以不可能看到别人的手牌

另有:
    encode_oracle(game, seat)  别人的手牌、牌墙里剩的牌、里宝。只给训练时的价值头用
    danger_labels(game, seat)  现在打出每种牌会不会被荣和(看全场算出来的标签),训练点炮头用
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from riichi.game import NUM_SEATS, NUM_TILES, Game, Phase
from riichi.hand import waits
from riichi.tiles import dora_of, kind_of

N = 34

# (名字, 通道数, 说明, 最大值)。顺序就是通道顺序,改动它等于换了一种输入格式,旧模型不能再用。
CHANNEL_GROUPS: Tuple[Tuple[str, int, str, int], ...] = (
    ("hand", 4, "自己的手牌: 第 k 个通道表示这种牌至少有 k 张", 1),
    ("red", 1, "自己手里的赤 5", 1),
    ("drawn", 1, "刚摸的那张", 1),
    ("meld", 16, "四家副露里的牌,每家 4 个通道: 至少 k 张", 1),
    ("discard", 16, "四家的弃牌(含被吃碰走的),每家 4 个通道: 至少 k 张", 1),
    ("riichi_tile", 4, "四家的立直宣言牌", 1),
    ("last_discard", 4, "四家各自最近打出的一张", 1),
    ("dora", 1, "宝牌: 这种牌是几重宝牌", 4),
    ("unseen", 4, "没见过的张数: 第 k 个通道表示至少还有 k 张没露面", 1),
    ("pending", 1, "等我响应的那张(别人打出的,或要杠的)", 1),
    ("kuikae", 1, "刚吃碰完不能打的牌", 1),
    ("yakuhai", 1, "对我来说是役牌的字牌(三元牌、自风、场风)", 1),
    # 以下是标量,整个通道填同一个数
    ("phase", 4, "阶段: 自己的回合、选立直宣言牌、响应弃牌、抢杠", 1),
    ("riichi", 4, "四家是否立直", 1),
    ("dealer", 4, "庄家在哪个相对座位", 1),
    ("score", 4, "四家点数(千点,0..100)", 100),
    ("round", 1, "第几局: 场风 × 4 + 局数", 11),
    ("honba", 1, "本场数(封顶 10)", 10),
    ("sticks", 1, "供托的立直棒数(封顶 10)", 10),
    ("wall", 1, "还能摸的牌数", 70),
    ("furiten", 1, "自己振听", 1),
    ("pending_from", 3, "等我响应的牌来自下家、对家还是上家", 1),
    ("pending_kind", 2, "那张牌是加杠的、暗杠的(都不是就是弃牌)", 1),
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
OBS_SCALE = np.asarray(_scale, dtype=np.float32)

ORACLE_CHANNELS = 17  # 三个对手的手牌(各 4 个通道)+ 牌墙里剩的牌(4)+ 里宝(1)
ORACLE_SHAPE = (ORACLE_CHANNELS, N)

_PHASES = {"TURN": 0, "RIICHI": 1, "RESPONSE": 2, "ROB_KAN": 3}
_SIZE = NUM_CHANNELS * N


def _o(name: str) -> int:
    return CHANNEL_OFFSET[name] * N


def _write(f: Dict[str, Any]) -> np.ndarray:
    """两个入口共用的写入部分。f 里的座位都是绝对座位,这里统一转成相对座位。"""
    buf = bytearray(_SIZE)
    seat = f["seat"]
    hand_counts = [0] * N
    for t in f["hand"]:
        hand_counts[kind_of(t)] += 1
        if t >= 34:
            buf[_o("red") + kind_of(t)] = 1
    seen = list(hand_counts)
    base = _o("hand")
    for k in range(N):
        for j in range(hand_counts[k]):
            buf[base + j * N + k] = 1
    if f["drawn"] is not None:
        buf[_o("drawn") + kind_of(f["drawn"])] = 1

    for rel in range(NUM_SEATS):
        s = (seat + rel) % NUM_SEATS
        counts = [0] * N
        for tiles in f["melds"][s]:
            for t in tiles:
                counts[kind_of(t)] += 1
        base = _o("meld") + rel * 4 * N
        for k in range(N):
            for j in range(min(counts[k], 4)):
                buf[base + j * N + k] = 1
            seen[k] += counts[k]
        counts = [0] * N
        for t, flags in zip(f["discards"][s], f["flags"][s]):
            k = kind_of(t)
            counts[k] += 1
            if not flags[2]:  # 被吃碰走的已经算在副露里
                seen[k] += 1
            if flags[1]:
                buf[_o("riichi_tile") + rel * N + k] = 1
        base = _o("discard") + rel * 4 * N
        for k in range(N):
            for j in range(min(counts[k], 4)):
                buf[base + j * N + k] = 1
        if f["discards"][s]:
            buf[_o("last_discard") + rel * N + kind_of(f["discards"][s][-1])] = 1

    for ind in f["dora_indicators"]:
        k = kind_of(ind)
        seen[k] += 1
        d = _o("dora") + dora_of(k)
        buf[d] = min(4, buf[d] + 1)
    base = _o("unseen")
    for k in range(N):
        left = 4 - seen[k]
        for j in range(max(0, min(left, 4))):
            buf[base + j * N + k] = 1
    pending = f["pending"]
    if pending is not None:
        buf[_o("pending") + kind_of(pending[1])] = 1
    for k in f["kuikae"]:
        buf[_o("kuikae") + k] = 1
    seat_wind = (seat - f["dealer"]) % NUM_SEATS
    for k in (31, 32, 33, 27 + seat_wind, 27 + f["round_wind"] % 4):
        buf[_o("yakuhai") + k] = 1

    def fill(name: str, idx: int, value: int) -> None:
        if value:
            start = _o(name) + idx * N
            buf[start : start + N] = bytes([value]) * N

    ph = _PHASES.get(f["phase"])
    if ph is not None:
        fill("phase", ph, 1)
    for rel in range(NUM_SEATS):
        s = (seat + rel) % NUM_SEATS
        fill("riichi", rel, 1 if f["riichi"][s] else 0)
        fill("score", rel, max(0, min(100, f["scores"][s] // 1000)))
    fill("dealer", (f["dealer"] - seat) % NUM_SEATS, 1)
    fill("round", 0, min(11, f["round_wind"] * 4 + f["kyoku"]))
    fill("honba", 0, min(10, f["honba"]))
    fill("sticks", 0, min(10, f["sticks"]))
    fill("wall", 0, max(0, min(70, f["wall"])))
    fill("furiten", 0, 1 if f["furiten"] else 0)
    if pending is not None:
        rel = (pending[0] - seat) % NUM_SEATS
        if rel:
            fill("pending_from", rel - 1, 1)
        if pending[2] == "kakan":
            fill("pending_kind", 0, 1)
        elif pending[2] == "ankan":
            fill("pending_kind", 1, 1)
    return np.frombuffer(buf, dtype=np.uint8).reshape(NUM_CHANNELS, N)


def _features(game: Game, seat: int) -> Dict[str, Any]:
    mine = game.current == seat and not game.is_over
    pending = None
    if game.pending is not None and game.phase in (Phase.RESPONSE, Phase.ROB_KAN):
        pending = game.pending
    return {
        "seat": seat,
        "phase": game.phase.name,
        "hand": game.hand_tiles(seat),
        "drawn": game.drawn if mine and game.phase in (Phase.TURN, Phase.RIICHI) else None,
        "melds": [[m.tiles for m in ms] for ms in game.melds],
        "discards": game.discards,
        "flags": game.discard_flags,
        "dora_indicators": game.dora_indicators(),
        "pending": pending,
        "kuikae": list(game.kuikae) if mine else [],
        "dealer": game.dealer,
        "round_wind": game.round_wind,
        "kyoku": game.kyoku,
        "honba": game.honba,
        "sticks": game.sticks,
        "riichi": game.riichi,
        "scores": game.scores,
        "wall": game.wall_remaining,
        "furiten": game._is_furiten(seat) if not game.is_over else False,
    }


def encode(game: Game, seat: int) -> np.ndarray:
    """训练用: 直接读引擎内部状态。只读这个座位按规则能看到的东西。"""
    return _write(_features(game, seat))


def encode_obs(obs: Dict[str, Any]) -> np.ndarray:
    """对局软件用: 只用 observation() 的字典。"""
    pending = obs.get("pending")
    return _write(
        {
            "seat": obs["seat"],
            "phase": obs["phase"],
            "hand": obs["hand"],
            "drawn": obs["drawn"],
            "melds": [[m["tiles"] for m in ms] for ms in obs["melds"]],
            "discards": obs["discards"],
            "flags": obs["discard_flags"],
            "dora_indicators": obs["dora_indicators"],
            "pending": None if pending is None else (pending["seat"], pending["tile"], pending["kind"]),
            "kuikae": obs["kuikae"],
            "dealer": obs["dealer"],
            "round_wind": obs["round_wind"],
            "kyoku": obs["kyoku"],
            "honba": obs["honba"],
            "sticks": obs["sticks"],
            "riichi": obs["riichi"],
            "scores": obs["scores"],
            "wall": obs["wall_remaining"],
            "furiten": obs["furiten"],
        }
    )


def encode_oracle(game: Game, seat: int) -> np.ndarray:
    """看全场的额外输入: 三个对手的手牌、牌墙里还没摸的牌、里宝。只给训练时的价值头用。"""
    out = np.zeros(ORACLE_SHAPE, dtype=np.uint8)
    for rel in range(1, NUM_SEATS):
        h = game.hands[(seat + rel) % NUM_SEATS]
        for k in range(N):
            n = h[k]
            if n:
                out[(rel - 1) * 4 : (rel - 1) * 4 + min(n, 4), k] = 1
    counts = [0] * N
    for t in game.wall[game.draw_pos : NUM_TILES - 14]:
        counts[kind_of(t)] += 1
    for k in range(N):
        if counts[k]:
            out[12 : 12 + min(counts[k], 4), k] = 1
    for ind in game.ura_indicators():
        out[16, dora_of(kind_of(ind))] = 1
    return out


def danger_labels(game: Game, seat: int) -> np.ndarray:
    """(34,) uint8: 现在打出这种牌,有没有别家能荣和(听这张、不振听、有役)。看全场才算得出,只做训练标签。"""
    out = np.zeros(N, dtype=np.uint8)
    for rel in range(1, NUM_SEATS):
        p = (seat + rel) % NUM_SEATS
        w = waits(game.hands[p], len(game.melds[p]))
        if not w or game._is_furiten(p):
            continue
        for k in w:
            if not out[k] and game._win_value(p, k, False) is not None:
                out[k] = 1
    return out


def legal_mask(ids: Sequence[int], size: int) -> np.ndarray:
    m = np.zeros(size, dtype=np.bool_)
    m[list(ids)] = True
    return m

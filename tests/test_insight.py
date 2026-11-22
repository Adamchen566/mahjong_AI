"""牌理: 向听数、进张、听牌提示。"""
import random
from functools import lru_cache

from chuanma import Game, RandomAgent, SimpleAgent
from chuanma.hand import is_win, winning_tiles
from chuanma.insight import insight, true_shanten, unseen_counts
from chuanma.tiles import parse_tiles, tiles_to_counts

MAN, PIN, SOU = 0, 1, 2


def c(text):
    return tiles_to_counts(parse_tiles(text))


def obs_of(hand, void=SOU, melds=(), discards=((), (), (), ()), phase="RESPONSE", seat=0):
    return {
        "seat": seat,
        "phase": phase,
        "hand": parse_tiles(hand),
        "void": [void, MAN, MAN, MAN],
        "won": [False] * 4,
        "melds": [list(melds), [], [], []],
        "discards": [parse_tiles(d) if isinstance(d, str) else list(d) for d in discards],
    }


# ---------------------------------------------------------------- 向听数


def brute_shanten(counts, void, limit=3):
    """按定义硬算 13 张型的向听数: 最少再摸几张有用的牌才能听。只用于测试。"""

    @lru_cache(maxsize=None)
    def tenpai(key):
        hand = list(key)
        if any(hand[void * 9 : void * 9 + 9]):
            return False
        for t in range(27):
            if t // 9 != void and hand[t] < 4:
                hand[t] += 1
                ok = is_win(hand, 0)
                hand[t] -= 1
                if ok:
                    return True
        return False

    frontier = {tuple(counts)}
    for depth in range(limit + 1):
        if any(tenpai(k) for k in frontier):
            return depth
        nxt = set()
        for key in frontier:
            hand = list(key)
            for t in range(27):
                if hand[t] >= 4:
                    continue
                hand[t] += 1
                for d in range(27):
                    if hand[d] and d != t:
                        hand[d] -= 1
                        nxt.add(tuple(hand))
                        hand[d] += 1
                hand[t] -= 1
        frontier = nxt
    return limit + 1


def test_void_tiles_cost_one_turn_each():
    # 四组面子都齐了,但还捏着一张缺门牌: 要先摸一张、打掉缺门,才算听牌
    assert true_shanten(c("123m456m789m123p5s"), 0, SOU) == 1
    assert true_shanten(c("123m456m789m12p55s"), 0, SOU) == 2
    # 没有缺门牌时和原来的算法一样
    assert true_shanten(c("123m456m789m13p99p"), 0, SOU) == 0
    # 14 张型: 马上就能打掉一张缺门牌
    assert true_shanten(c("123m456m789m13p99p5s"), 0, SOU) == 0


def test_true_shanten_matches_brute_force():
    rng = random.Random(7)
    checked = 0
    while checked < 12:
        # 造接近成型的牌: 几组顺子刻子,加几张散牌,再混进 0 到 2 张缺门牌
        hand = [0] * 27
        for _ in range(rng.choice((2, 3))):
            suit, rank = rng.randrange(2), rng.randrange(7)
            for k in range(3):
                hand[suit * 9 + rank + k] += 1
        void_n = rng.randrange(3)
        while sum(hand) < 13 - void_n:
            t = rng.randrange(18)
            if hand[t] < 4:
                hand[t] += 1
        for _ in range(void_n):
            hand[18 + rng.randrange(9)] += 1
        if max(hand) > 4 or sum(hand) != 13:
            continue
        got = true_shanten(hand, 0, SOU)
        if got > 2:
            continue
        assert got == brute_shanten(hand, SOU, limit=2), hand
        checked += 1


# ---------------------------------------------------------------- 听牌、进张


def test_waits_come_with_remaining_count_and_fan():
    # 听 2 筒: 自己没有,对家打过一张,还剩 3 张
    info = insight(obs_of("123m456m789m13p99p", discards=("", "2p", "", "")))
    assert info["shanten"] == 0 and info["void_left"] == 0
    assert [(w["tile"], w["left"]) for w in info["waits"]] == [(parse_tiles("2p")[0], 3)]
    assert info["total"] == 3
    w = info["waits"][0]
    assert w["points"] == 2 ** w["fan"] and w["names"]


def test_useful_tiles_when_not_ready():
    info = insight(obs_of("123m456m789m1p99p5p"))
    assert info["shanten"] == 1 and "waits" not in info
    tiles = {u["tile"] for u in info["useful"]}
    assert set(parse_tiles("2p3p4p6p7p9p")) <= tiles
    assert info["total"] == sum(u["left"] for u in info["useful"])


def test_each_discard_is_rated_on_your_turn():
    info = insight(obs_of("123m456m789m13p99p5p", phase="TURN"))
    by_tile = {o["tile"]: o for o in info["discards"]}
    five = by_tile[parse_tiles("5p")[0]]
    assert info["shanten"] == 0 and five["shanten"] == 0 and five["best"]
    assert [w["tile"] for w in five["waits"]] == parse_tiles("2p")
    # 拆掉一组顺子就退回一向听
    assert by_tile[parse_tiles("1m")[0]]["shanten"] == 1
    assert sum(o["best"] for o in info["discards"]) >= 1


def test_must_discard_void_first():
    info = insight(obs_of("123m456m789m13p99p5s", phase="TURN"))
    assert info["void_left"] == 1
    assert [o["tile"] for o in info["discards"]] == parse_tiles("5s")


def test_no_insight_before_play_or_after_winning():
    assert insight(obs_of("123m456m789m13p99p", phase="EXCHANGE")) is None
    won = obs_of("123m456m789m13p99p")
    won["won"][0] = True
    assert insight(won) is None


def test_unseen_counts_only_use_what_the_seat_can_see():
    obs = obs_of("11m", discards=("1m", "", "2p2p", ""), melds=[{"type": "PONG", "tile": 9, "from_seat": 1}])
    obs["melds"][2] = [{"type": "AN_GANG", "tile": None, "from_seat": 2}]  # 别人的暗杠看不到
    left = unseen_counts(obs)
    assert left[0] == 1 and left[9] == 1 and left[10] == 2 and left[26] == 4


def test_insight_agrees_with_the_engine_in_real_games():
    """整局跑下来: 说听牌的时候确实听牌,说的每一张能胡的牌确实能胡。"""
    seen_ready = 0
    for seed in range(6):
        game = Game(seed=seed)
        agents = [SimpleAgent() if s % 2 else RandomAgent(seed + s) for s in range(4)]
        while not game.is_over:
            seat = game.current
            obs = game.observation(seat)
            info = insight(obs)
            if info is not None and "discards" not in info:
                counts = tiles_to_counts(obs["hand"])
                melds = obs["melds"][seat]
                meld_tiles = [m["tile"] for m in melds for _ in range(4 if "GANG" in m["type"] else 3)]
                waits = winning_tiles(counts, len(melds), obs["void"][seat], meld_tiles)
                if info["shanten"] == 0:
                    seen_ready += 1
                    assert [w["tile"] for w in info["waits"]] == waits
                else:
                    assert not waits
            game.step(agents[seat].act(obs, game.legal_actions()))
    assert seen_ready > 0


# ---------------------------------------------------------------- 危险度


def danger_obs(tile_text="5p", **changes):
    """对家打了 12 张牌、碰了两组,另外两家刚开局。自己手里有一张 tile_text。"""
    obs = obs_of("123m456m789m13p99p" + tile_text, phase="TURN")
    obs["void"] = [SOU, MAN, SOU, SOU]
    obs["discards"] = [[], [], parse_tiles("1s2s3s4s6s7s8s9s1s2s3s4s"), []]
    obs["melds"][2] = [{"type": "PONG", "tile": 0, "from_seat": 0}, {"type": "PONG", "tile": 8, "from_seat": 1}]
    obs.update(changes)
    return obs


def test_danger_is_zero_against_a_void_suit_or_a_finished_player():
    from chuanma.danger import danger

    tile = parse_tiles("5m")[0]
    obs = danger_obs("5m")
    seats = [seat for seat, _ in danger(obs, tile)["by"]]
    assert 1 not in seats and set(seats) == {2, 3}  # 下家缺万,不可能胡万子
    obs["won"] = [False, False, True, False]
    assert [seat for seat, _ in danger(obs, tile)["by"]] == [3]
    obs["won"] = [False, True, True, True]
    assert danger(obs, tile) == {"p": 0.0, "by": []}


def test_danger_grows_with_turns_and_melds_and_drops_for_tiles_they_threw():
    from chuanma.danger import danger

    tile = parse_tiles("5p")[0]
    late = dict(danger(danger_obs(), tile)["by"])
    assert late[2] > 4 * late[3]  # 打了 12 张、碰了两组的对家,比刚开局的上家危险得多
    thrown = danger_obs()
    thrown["discards"][2] = thrown["discards"][2][:-1] + [tile]
    assert dict(danger(thrown, tile)["by"])[2] < late[2] / 2  # 对家自己打过这张
    total = danger(danger_obs(), tile)["p"]
    assert max(late.values()) <= total <= sum(late.values())


def test_every_discard_option_carries_its_danger():
    info = insight(danger_obs())
    assert all(0 <= o["danger"]["p"] <= 1 for o in info["discards"])
    by_tile = {o["tile"]: o["danger"]["p"] for o in info["discards"]}
    # 同样的对手、同样没见过: 中张比幺九更容易点炮
    assert by_tile[parse_tiles("5p")[0]] > by_tile[parse_tiles("9p")[0]]


def test_danger_table_was_checked_against_held_out_games():
    from chuanma.danger import load_table

    table = load_table()
    assert table["games"] >= 10000
    for row in table["holdout"]:
        assert abs(row["predicted"] - row["actual"]) < 0.25 * row["actual"] + 0.002

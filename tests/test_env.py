"""并行对局环境和模仿数据生成。"""
import numpy as np

from ai.encoding import NUM_CHANNELS, ORACLE_SHAPE
from ai.env import BatchEnv, ParallelEnv, SeatPlan
from ai.generate import generate, load_shard
from chuanma import NUM_ACTIONS, SimpleAgent, play_game


def random_policy(mask, rng):
    return [int(rng.choice(np.flatnonzero(row))) for row in mask]


def run(env, ticks, seed=0):
    rng = np.random.default_rng(seed)
    episodes = []
    for _ in range(ticks):
        batch = env.observe()
        assert batch.mask.any(axis=1).all()  # 每个位置都有决定可做
        assert (batch.mask.sum(axis=1) >= 2).all()  # 只有一个选择的局面不会交出来
        episodes.extend(env.step(random_policy(batch.mask, rng)))
    return episodes


def check_episode(ep):
    t = len(ep)
    assert t > 0
    assert ep.obs.shape == (t, NUM_CHANNELS, 27) and ep.obs.dtype == np.uint8
    assert ep.mask.shape == (t, NUM_ACTIONS)
    assert ep.mask[np.arange(t), ep.action].all()  # 记下的动作都是合法的
    assert ep.reward.sum() == ep.final_score  # 每步得分变化加起来就是终局得分


def test_batch_env_produces_valid_episodes():
    env = BatchEnv(6, seed=3)
    episodes = run(env, 800)
    assert env.stats.games > 5 and env.stats.decisions == 800 * 6
    for ep in episodes:
        check_episode(ep)
    # 同一局的四个座位得分和为 0
    by_seed = {}
    for ep in episodes:
        by_seed.setdefault(ep.seed, []).append(ep)
    full = [eps for eps in by_seed.values() if len(eps) == 4]
    assert full and all(sum(e.final_score for e in eps) == 0 for eps in full)


def test_batch_env_is_deterministic():
    a = run(BatchEnv(4, seed=11), 300, seed=5)
    b = run(BatchEnv(4, seed=11), 300, seed=5)
    assert len(a) == len(b) > 0
    for x, y in zip(a, b):
        assert (x.seed, x.seat, x.final_score) == (y.seed, y.seat, y.final_score)
        assert np.array_equal(x.obs, y.obs) and np.array_equal(x.action, y.action)


def test_batch_env_plays_the_same_game_as_the_runner():
    """外部策略照 SimpleAgent 的选择走,结果要和 play_game 直接打出来的一样。"""
    env = BatchEnv(3, seed=20)
    agent = SimpleAgent()
    episodes = []
    while len({e.seed for e in episodes}) < 6:
        actions = [
            agent.act(g.observation(g.current), g.legal_actions()).id for g in env.games
        ]
        episodes.extend(env.step(actions))
    for ep in episodes:
        ref = play_game([SimpleAgent() for _ in range(4)], seed=ep.seed, dealer=ep.seed % 4)
        assert ref.scores[ep.seat] == ep.final_score


def test_seat_plan_with_fixed_opponents():
    env = BatchEnv(4, seed=1, plan=SeatPlan(learners=1, opponents=("simple", "rule")), oracle=True)
    episodes = run(env, 400)
    assert episodes
    seeds = [e.seed for e in episodes]
    assert len(seeds) == len(set(seeds))  # 每局只有一个座位交给外部策略
    assert len({e.seat for e in episodes}) > 1  # 座位是随机挑的
    for ep in episodes:
        check_episode(ep)
        assert ep.oracle.shape == (len(ep), *ORACLE_SHAPE)


def test_logp_and_value_are_carried_back():
    env = BatchEnv(2, seed=9)
    rng = np.random.default_rng(0)
    episodes = []
    tick = 0
    while not episodes:
        batch = env.observe()
        tick += 1
        episodes = env.step(random_policy(batch.mask, rng), logp=[-tick, -tick], value=[tick, tick])
    ep = episodes[0]
    assert (ep.value > 0).all() and np.array_equal(ep.logp, -ep.value)
    assert (np.diff(ep.value) > 0).all()


def test_parallel_env():
    with ParallelEnv(num_workers=2, games_per_worker=3, seed=100) as env:
        assert env.observe().obs.shape == (6, NUM_CHANNELS, 27)
        episodes = run(env, 500)
        stats = env.stats
    assert stats.games > 5 and stats.decisions == 500 * 6
    for ep in episodes:
        check_episode(ep)
    keys = [(e.seed, e.seat) for e in episodes]
    assert len(keys) == len(set(keys))  # 两个进程的种子不重复


def test_generate_dataset(tmp_path):
    meta = generate(str(tmp_path), num_games=6, teacher="simple", seed=40, shard_games=4)
    assert meta["shards"] == 2 and meta["games"] == 6 and meta["samples"] > 100
    shards = sorted(tmp_path.glob("shard_*.npz"))
    assert len(shards) == 2
    total = 0
    for path in shards:
        data = load_shard(str(path))
        n = len(data["action"])
        total += n
        assert data["obs"].shape == (n, NUM_CHANNELS, 27)
        assert data["oracle"].shape == (n, *ORACLE_SHAPE)
        assert data["mask"].shape == (n, NUM_ACTIONS)
        assert data["mask"][np.arange(n), data["action"]].all()
        assert (data["mask"].sum(axis=1) >= 2).all()
        # 每局每个座位的第一个决策点: 此时得分还是 0,所以"还会得多少分"就是终局得分
        first = {}
        for k in range(n):
            first.setdefault((int(data["seed"][k]), int(data["seat"][k])), int(data["ret"][k]))
        for (seed, seat), ret in first.items():
            ref = play_game([SimpleAgent() for _ in range(4)], seed=seed, dealer=seed % 4)
            assert ref.scores[seat] == ret
    assert total == meta["samples"]


def test_generate_with_exploration_keeps_teacher_labels_legal(tmp_path):
    generate(str(tmp_path), num_games=4, teacher="rule", seed=7, explore=0.3)
    data = load_shard(str(tmp_path / "shard_00000.npz"))
    n = len(data["action"])
    assert n > 50 and data["mask"][np.arange(n), data["action"]].all()

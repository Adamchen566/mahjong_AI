"""自我对弈: 优势计算、对手池、PPO 更新、断点续训。没装 PyTorch 时整个文件跳过。"""
import math

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai.env import BatchEnv, SeatPlan  # noqa: E402
from ai.model import MahjongNet, ModelConfig, load_checkpoint, save_checkpoint  # noqa: E402
from ai.ppo import build_rollout, gae, ppo_update  # noqa: E402
from ai.train_ppo import act, train  # noqa: E402

SMALL = ModelConfig(channels=32, blocks=2, hidden=64)
CPU = torch.device("cpu")


def test_gae_by_hand():
    reward = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    value = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    # lam=1: 优势 = 实际拿到的总回报 − 估计
    adv, ret = gae(reward, value, lam=1.0)
    assert adv.tolist() == [0.5, 0.5, 0.5] and ret.tolist() == [1.0, 1.0, 1.0]
    # lam=0: 只看一步。前两步"估计没变、没得分"所以是 0;最后一步得 1 分、之后是终局
    adv, ret = gae(reward, value, lam=0.0)
    assert adv.tolist() == [0.0, 0.0, 0.5]
    # 中间值: 最后一步的意外按 lam 的幂次往前传
    adv, _ = gae(reward, value, lam=0.5)
    assert np.allclose(adv, [0.125, 0.25, 0.5])


def test_pool_games_mix_policies_and_only_track_the_learner():
    env = BatchEnv(6, seed=2, plan=SeatPlan(pool_size=3, pool_prob=1.0), oracle=True)
    rng = np.random.default_rng(0)
    seen = set()
    episodes = []
    for _ in range(600):
        batch = env.observe()
        seen.update(batch.policy.tolist())
        actions = [int(rng.choice(np.flatnonzero(row))) for row in batch.mask]
        episodes.extend(env.step(actions))
    assert seen == {0, 1, 2, 3}
    assert episodes and all(e.opponents in (2, 3) for e in episodes)
    per_game = {}
    for e in episodes:
        per_game[e.seed] = per_game.get(e.seed, 0) + 1
    assert max(per_game.values()) <= 2  # 每局最多两个座位是要训练的策略


def sample_episodes(model, pool, n=400):
    env = BatchEnv(8, seed=5, plan=SeatPlan(pool_size=len(pool), pool_prob=0.5 if pool else 0.0), oracle=True)
    episodes = []
    while sum(len(e) for e in episodes) < n:
        episodes.extend(env.step(*act(model, pool, env.observe(), CPU)))
    return episodes


def test_act_records_logp_and_value_for_the_learner():
    torch.manual_seed(0)
    model = MahjongNet(SMALL).eval()
    pool = [MahjongNet(SMALL).eval()]
    episodes = sample_episodes(model, pool)
    for ep in episodes:
        assert (ep.logp < 0).all()  # 采样出来的动作概率小于 1
        assert ep.mask[np.arange(len(ep)), ep.action].all()
    # 记下来的对数概率就是当前模型对那个动作给的
    ep = episodes[0]
    with torch.no_grad():
        out = model(torch.from_numpy(ep.obs), torch.from_numpy(ep.mask), torch.from_numpy(ep.oracle))
    logp = torch.log_softmax(out.logits, 1)[torch.arange(len(ep)), torch.from_numpy(ep.action).long()]
    assert np.allclose(logp.numpy(), ep.logp, atol=1e-4)
    assert np.allclose(out.oracle_value.numpy(), ep.value, atol=1e-4)


def test_ppo_update_runs_and_changes_the_policy():
    torch.manual_seed(1)
    model = MahjongNet(SMALL).eval()
    data = build_rollout(sample_episodes(model, []), CPU)
    assert len(data) >= 400 and data.adv.shape == data.ret.shape == data.logp.shape
    before = [p.clone() for p in model.parameters()]
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    scaler = torch.amp.GradScaler(enabled=False)
    metrics = ppo_update(model, opt, scaler, data, epochs=2, batch_size=128)
    assert all(math.isfinite(v) for v in metrics.values())
    assert metrics["entropy"] > 0 and metrics["updates"] >= 4
    assert any(not torch.equal(a, b) for a, b in zip(before, model.parameters()))


def test_train_saves_and_resumes(tmp_path):
    init = tmp_path / "init.pt"
    save_checkpoint(init, MahjongNet(SMALL))
    out = tmp_path / "ppo"
    common = dict(
        rollout_decisions=300,
        workers=1,
        games_per_worker=6,
        batch_size=128,
        pool_size=2,
        snapshot_every=1,
        eval_every=0,
        device="cpu",
        log=lambda *_: None,
    )
    train(str(out), init=str(init), iterations=2, **common)
    first = load_checkpoint(out / "latest.pt")
    assert first["state"]["iteration"] == 2 and first["state"]["games"] > 0
    assert len(first["pool"]) == 2 and "optimizer" in first

    train(str(out), resume=True, iterations=1, **common)
    second = load_checkpoint(out / "latest.pt")
    assert second["state"]["iteration"] == 3
    assert second["state"]["games"] > first["state"]["games"]
    rows = (out / "log.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1 + 3  # 表头 + 三轮,续训是接着写的

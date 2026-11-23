"""日麻训练代码的小规模测试: 环境的轨迹和回报、网络形状、模仿学习和 PPO 各跑通一小步。"""
import numpy as np
import pytest

torch = pytest.importorskip("torch")

from riichi.actions import NUM_ACTIONS  # noqa: E402
from riichi_ai.encoding import NUM_CHANNELS, ORACLE_CHANNELS  # noqa: E402
from riichi_ai.env import BatchEnv, SeatPlan  # noqa: E402
from riichi_ai.model import ModelConfig, RiichiNet  # noqa: E402
from riichi_ai.ppo import build_rollout, gae, ppo_update  # noqa: E402

TINY = ModelConfig(channels=16, blocks=1, head_channels=8, hidden=32)


def random_rollout(env, steps_limit=200000):
    rng = np.random.default_rng(0)
    episodes = []
    steps = 0
    while not episodes and steps < steps_limit:
        batch = env.observe()
        actions = [rng.choice(np.flatnonzero(m)) for m in batch.mask]
        episodes = env.step(actions)
        steps += 1
    return episodes


def test_batch_env_episode_rewards_sum_to_final_points():
    env = BatchEnv(2, seed=3, plan=SeatPlan(learners=4), oracle=True)
    episodes = random_rollout(env)
    assert len(episodes) == 4  # 一场打完,四个座位各一条
    for ep in episodes:
        T = len(ep)
        assert ep.obs.shape == (T, NUM_CHANNELS, 34) and ep.oracle.shape == (T, ORACLE_CHANNELS, 34)
        assert ep.mask.shape == (T, NUM_ACTIONS) and ep.mask[np.arange(T), ep.action].all()
        assert ep.danger.shape == (T, 34) and ep.has_danger.sum() > 0
    # 四家名次分之和为 0;每条轨迹的回报之和 = 名次分 − 第一次决定时的 (点数 − 25000)/1000
    assert abs(sum(e.final_points for e in episodes)) < 1e-6
    assert sorted(e.rank for e in episodes) == [0, 1, 2, 3]
    for ep in episodes:
        # 第一次决定在第一局开头,那时点数还是 25000
        assert ep.reward.sum() == pytest.approx(ep.final_points, abs=1e-3)


def test_fixed_opponents_are_not_recorded():
    env = BatchEnv(1, seed=5, plan=SeatPlan(learners=1, opponents=("simple",)))
    episodes = random_rollout(env)
    assert len(episodes) == 1 and episodes[0].opponents == 3


def test_model_shapes_and_mask():
    net = RiichiNet(TINY)
    obs = torch.zeros(3, NUM_CHANNELS, 34, dtype=torch.uint8)
    mask = torch.zeros(3, NUM_ACTIONS, dtype=torch.bool)
    mask[:, :5] = True
    out = net(obs, mask, torch.zeros(3, ORACLE_CHANNELS, 34, dtype=torch.uint8))
    assert out.logits.shape == (3, NUM_ACTIONS) and out.value.shape == (3,) and out.danger.shape == (3, 34)
    assert torch.isinf(out.logits[:, 5:]).all() and out.oracle_value.shape == (3,)
    # 策略、价值、点炮头不依赖看全场的输入
    out2 = net(obs, mask, torch.ones(3, ORACLE_CHANNELS, 34, dtype=torch.uint8))
    assert torch.equal(out.logits, out2.logits) and torch.equal(out.danger, out2.danger)


def test_gae_lambda_one_is_monte_carlo():
    r = np.array([1.0, 0.0, 2.0], dtype=np.float32)
    v = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    adv, ret = gae(r, v, lam=1.0)
    assert np.allclose(ret, [3.0, 2.0, 2.0])


def test_ppo_update_runs():
    env = BatchEnv(1, seed=7, plan=SeatPlan(learners=4), oracle=True)
    episodes = random_rollout(env)
    data = build_rollout(episodes, torch.device("cpu"))
    net = RiichiNet(TINY)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    scaler = torch.amp.GradScaler(enabled=False)
    metrics = ppo_update(net, opt, scaler, data, epochs=1, batch_size=256)
    assert metrics["updates"] >= 1 and np.isfinite(metrics["policy_loss"]) and np.isfinite(metrics["danger_loss"])


def test_generate_and_train_bc_tiny(tmp_path):
    from riichi_ai.generate import generate
    from riichi_ai.train_bc import train

    generate(str(tmp_path / "d"), 1, teacher="simple", shard_games=1)
    generate(str(tmp_path / "v"), 1, teacher="simple", seed=99, shard_games=1)
    last = train([str(tmp_path / "d")], [str(tmp_path / "v")], str(tmp_path / "ck"), epochs=0.2, batch_size=64,
                 config=TINY, device="cpu", eval_every=5, log=lambda *a: None)
    assert 0 <= last["accuracy"] <= 1 and (tmp_path / "ck" / "best.pt").is_file()


def test_export_onnx_agent_hint_and_analysis(tmp_path):
    """小网络导出成 ONNX: 推理结果和 PyTorch 一致;对局里的提示、观战、复盘分析都能用它。"""
    pytest.importorskip("onnxruntime")
    from riichi import Game
    from riichi_ai.encoding import encode_obs
    from riichi_ai.export import export_onnx
    from riichi_ai.model import save_checkpoint
    from riichi_ai.onnx_agent import OnnxAgent
    from server.riichi_match import RiichiMatch, advise
    from server.riichi_records import record_analysis, spectate_record

    torch.manual_seed(0)
    net = RiichiNet(TINY).eval()
    ck = tmp_path / "tiny.pt"
    save_checkpoint(ck, net, stage="test")
    onnx_path = export_onnx(str(ck), str(tmp_path / "tiny.onnx"))
    agent = OnnxAgent(onnx_path)
    game = Game(seed=1)
    obs = game.observation(0)
    legal = game.legal_actions()
    probs, value, danger = agent.evaluate(obs, legal)
    assert len(probs) == len(legal) and abs(sum(probs) - 1) < 1e-5 and len(danger) == 34
    with torch.no_grad():
        out = net(torch.from_numpy(encode_obs(obs)).unsqueeze(0))
    assert np.allclose(danger, torch.sigmoid(out.danger[0]).numpy(), atol=1e-4)

    match = RiichiMatch(opponent="simple", seed=3, advisor=agent)
    match.hint_on = True
    snap = match.snapshot()
    hint = snap["view"]["hint"]
    assert snap["match"]["hint_available"] and len(hint["choices"]) == 3 and len(hint["danger"]) == 34
    assert all(t in [a.arg for a in match.game.legal_actions()] for t, _ in hint["tiles"])
    assert advise(agent, match.game, 0)["value"] == hint["value"]

    rec = spectate_record(["simple", "simple", "simple", "simple"], seed=4)
    result = record_analysis(rec, agent)
    assert len(result["steps"]) == len(rec.actions)
    assert sum(s["decisions"] for s in result["summary"]) == sum(1 for s in result["steps"] if not s["forced"])

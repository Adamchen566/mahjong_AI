"""网络、模仿学习训练、把网络包成策略。没装 PyTorch 时整个文件跳过。"""
import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai import make_agent  # noqa: E402
from ai.dataset import Dataset  # noqa: E402
from ai.encoding import NUM_CHANNELS, ORACLE_SHAPE, encode, encode_oracle, legal_mask  # noqa: E402
from ai.generate import generate  # noqa: E402
from ai.model import MahjongNet, ModelConfig, load_model, save_checkpoint  # noqa: E402
from ai.net_agent import NetAgent  # noqa: E402
from ai.train_bc import train  # noqa: E402
from chuanma import NUM_ACTIONS, Game, SimpleAgent, play_game  # noqa: E402

SMALL = ModelConfig(channels=32, blocks=2, hidden=64)


def sample_batch(n=6):
    obs, oracle, mask = [], [], []
    game = Game(seed=3)
    while len(obs) < n:
        obs.append(encode(game, game.current))
        oracle.append(encode_oracle(game, game.current))
        mask.append(legal_mask(game))
        game.step(game.legal_action_ids()[-1])
    return (torch.from_numpy(np.stack(a)) for a in (obs, oracle, mask))


def test_model_shapes_and_mask():
    model = MahjongNet(SMALL).eval()
    obs, oracle, mask = sample_batch()
    out = model(obs, mask, oracle)
    assert out.logits.shape == (6, NUM_ACTIONS)
    assert out.value.shape == (6,) and out.oracle_value.shape == (6,)
    probs = torch.softmax(out.logits, dim=1)
    assert torch.allclose(probs.sum(1), torch.ones(6), atol=1e-5)
    assert (probs[~mask] == 0).all()  # 非法动作的概率为 0
    assert model(obs).oracle_value is None  # 不给全场信息就不算那一路


def test_policy_does_not_depend_on_oracle_input():
    """策略头和普通价值头只看自己座位的信息: 换掉别人的手牌,输出一点不变。"""
    model = MahjongNet(SMALL).eval()
    for p in model.parameters():  # 打乱参数,免得"初始化成 0"掩盖问题
        torch.nn.init.normal_(p, std=0.3)
    obs, oracle, mask = sample_batch()
    a = model(obs, mask, oracle)
    b = model(obs, mask, torch.randint(0, 2, oracle.shape, dtype=torch.uint8))
    assert torch.equal(a.logits, b.logits) and torch.equal(a.value, b.value)
    assert not torch.equal(a.oracle_value, b.oracle_value)


def test_checkpoint_roundtrip(tmp_path):
    model = MahjongNet(SMALL).eval()
    path = tmp_path / "m.pt"
    save_checkpoint(path, model, step=7)
    again = load_model(path)
    obs, oracle, mask = sample_batch()
    assert torch.equal(model(obs, mask).logits, again(obs, mask).logits)
    assert again.config == SMALL


def test_behaviour_cloning_learns_and_plays(tmp_path):
    """几局数据上训几十步: 损失要降,存下来的模型要能坐进牌局打完一局。"""
    generate(str(tmp_path / "train"), num_games=30, teacher="simple", seed=0)
    generate(str(tmp_path / "val"), num_games=6, teacher="simple", seed=500)
    data = Dataset([str(tmp_path / "train")])
    assert data.obs.shape[1:] == (NUM_CHANNELS, 27) and data.oracle.shape[1:] == ORACLE_SHAPE
    batch = next(data.batches(64))
    assert batch.mask[np.arange(64), batch.action].all()

    lines = []
    last = train(
        [str(tmp_path / "train")],
        [str(tmp_path / "val")],
        str(tmp_path / "ckpt"),
        epochs=6,
        batch_size=64,
        lr=2e-3,
        config=SMALL,
        device="cpu",
        eval_every=40,
        log=lines.append,
    )
    rows = (tmp_path / "ckpt" / "log.csv").read_text(encoding="utf-8").strip().splitlines()
    header = rows[0].split(",")
    col = header.index("policy_loss")
    first, final = float(rows[1].split(",")[col]), float(rows[-1].split(",")[col])
    assert final < first
    assert last["accuracy"] > 0.3  # 随机猜大约是 1/6

    path = str(tmp_path / "ckpt" / "best.pt")
    agent = make_agent(path, seed=1)
    assert isinstance(agent, NetAgent)
    game = play_game([agent] + [SimpleAgent() for _ in range(3)], seed=9)
    assert game.is_over and sum(game.scores) == 0


def test_net_agent_only_needs_the_observation(tmp_path):
    path = tmp_path / "m.pt"
    save_checkpoint(path, MahjongNet(SMALL))
    agent = NetAgent(str(path), greedy=False, seed=0)
    game = Game(seed=4)
    obs = game.observation(game.current)
    assert "hands" not in obs  # 对局中视图里没有别人的手牌
    legal = game.legal_actions()
    probs = agent.probabilities(obs, legal)
    assert len(probs) == len(legal) and abs(sum(probs) - 1) < 1e-5
    assert agent.act(obs, legal) in legal

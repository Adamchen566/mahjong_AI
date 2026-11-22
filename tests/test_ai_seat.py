"""AI 入座: 导出的模型、提示、复盘分析,以及"AI 拿不到别人的牌"。"""
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ai.encoding import encode, encode_obs
from chuanma import Game, GameRecord, SimpleAgent, play_game
from server import Match, create_app
from server.match import advise, record_analysis


class SpyAdvisor:
    """假模型: 记下它被问到的每个局面,永远最看好第一个合法动作。"""

    def __init__(self):
        self.seen = []

    def evaluate(self, obs, legal):
        self.seen.append(obs)
        n = len(legal)
        probs = [0.6] + [0.4 / (n - 1)] * (n - 1) if n > 1 else [1.0]
        return probs, 1.5


def play_until_human(match):
    while match.bot_to_act:
        match.bot_step()


# ---------------------------------------------------------------- 提示


def test_hint_is_off_by_default_and_only_shows_on_your_turn():
    spy = SpyAdvisor()
    match = Match(opponent="simple", seed=3, advisor=spy)
    match.start_game()
    play_until_human(match)
    snap = match.snapshot()
    assert snap["match"]["hint_available"] and not snap["match"]["hint_on"]
    assert "hint" not in snap["view"] and not spy.seen

    match.hint_on = True
    snap = match.snapshot()
    hint = snap["view"]["hint"]
    legal_ids = {a["id"] for a in snap["view"]["legal"]}
    assert {c["id"] for c in hint["choices"]} <= legal_ids
    probs = [c["prob"] for c in hint["choices"]]
    assert probs == sorted(probs, reverse=True) and len(probs) <= 3
    assert hint["value"] == 1.5 and all(c["text"] for c in hint["choices"])


def test_match_without_a_model_still_plays():
    match = Match(opponent="simple", seed=3)
    match.hint_on = True  # 没有模型时打开也没用
    match.start_game()
    play_until_human(match)
    snap = match.snapshot()
    assert not snap["match"]["hint_available"] and not snap["match"]["hint_on"]
    assert "hint" not in snap["view"]


def test_the_model_never_sees_other_players_tiles():
    """给提示的模型和入座的 AI,拿到的都只是那个座位自己的视图。"""
    spy = SpyAdvisor()
    match = Match(opponent="simple", seed=11, advisor=spy)
    match.hint_on = True
    seats_seen = []

    class SpyAgent(SimpleAgent):
        def act(self, obs, legal):
            seats_seen.append(obs)
            return super().act(obs, legal)

    match.agents = {s: SpyAgent() for s in match.agents}
    match.start_game()
    for _ in range(400):
        game = match.game
        if game.is_over:
            break
        if match.bot_to_act:
            seat = game.current
            before = len(seats_seen)
            match.bot_step()
            obs = seats_seen[before]
            assert obs["seat"] == seat  # 电脑拿到的是它自己座位的视图
        else:
            snap = match.snapshot()
            obs = spy.seen[-1]
            assert obs["seat"] == match.human_seat
            # 模型看到的编码,和"只读这个座位能看到的东西"的编码一模一样
            assert np.array_equal(encode_obs(obs), encode(game, match.human_seat))
            match.human_action(snap["view"]["hint"]["choices"][0]["id"])
    assert game.is_over and spy.seen and seats_seen
    for obs in spy.seen + seats_seen:
        assert "hands" not in obs  # 对局中的视图里没有四家手牌
        others = [m for s, row in enumerate(obs["melds"]) if s != obs["seat"] for m in row]
        assert all(m["tile"] is None for m in others if m["type"] == "AN_GANG")  # 别人的暗杠看不到牌


# ---------------------------------------------------------------- 复盘分析


def test_record_analysis_compares_each_decision():
    game = play_game([SimpleAgent() for _ in range(4)], seed=21, record_events=False)
    record = GameRecord.from_game(game)
    spy = SpyAdvisor()
    result = record_analysis(record, spy)
    steps = result["steps"]
    assert len(steps) == len(record.actions)
    free = [s for s in steps if not s["forced"]]
    assert len(free) == len(spy.seen) > 20
    for s in free:
        assert s["agree"] == (s["best"]["id"] == s["chosen"]["id"])
        assert s["best"]["prob"] >= s["chosen"]["prob"] and s["best"]["text"]
    for row in result["summary"]:
        mine = [s for s in free if s["seat"] == row["seat"]]
        assert row["decisions"] == len(mine)
        assert row["agreed"] == sum(s["agree"] for s in mine)
    # 分析时模型看到的是当时那个座位的视图,不是摊开的牌
    assert all("hands" not in obs for obs in spy.seen)


@pytest.fixture
def client(tmp_path):
    app = create_app(records_dir=tmp_path, dist_dir=tmp_path / "no-dist", bot_delay=0, seed=7, advisor=SpyAdvisor())
    with TestClient(app) as c:
        yield c


def play_to_end(ws, hint=False):
    msg = ws.receive_json()
    while True:
        view = msg["view"]
        if view["phase"] == "END":
            return msg
        if view["legal"]:
            if hint:
                assert msg["match"]["hint_on"] and view["hint"]["choices"]
            ws.send_json({"type": "action", "id": view["legal"][0]["id"]})
        msg = ws.receive_json()


def test_hint_over_websocket_and_analysis_over_http(client, tmp_path):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "new_match", "opponent": "simple"})
        ws.receive_json()
        ws.send_json({"type": "hint", "on": True})
        end = play_to_end(ws, hint=True)
    name = end["view"]["record"]
    data = client.get(f"/api/records/{name}/analysis").json()
    assert data["available"] and len(data["steps"]) == len(client.get(f"/api/records/{name}").json()["steps"])
    assert client.get("/api/records/nope.json/analysis").status_code == 404


def test_analysis_says_so_when_there_is_no_model(tmp_path):
    app = create_app(records_dir=tmp_path, dist_dir=tmp_path / "no-dist", bot_delay=0, advisor=None)
    with TestClient(app) as c:
        data = c.get("/api/records/whatever.json/analysis").json()
        assert data["available"] is False and data["reason"]
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"type": "new_match", "opponent": "simple"})
            ws.receive_json()
            ws.send_json({"type": "hint", "on": True})
            msgs = [ws.receive_json(), ws.receive_json()]
            assert any(m["type"] == "error" for m in msgs)


# ---------------------------------------------------------------- 导出的模型


def test_onnx_model_matches_pytorch_and_is_fast(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from ai import make_agent
    from ai.export import export_onnx
    from ai.model import MahjongNet, ModelConfig, save_checkpoint
    from ai.net_agent import NetAgent
    from ai.onnx_agent import OnnxAgent

    torch.manual_seed(0)
    ckpt = tmp_path / "m.pt"
    save_checkpoint(ckpt, MahjongNet(ModelConfig(channels=32, blocks=2, hidden=64)))
    path = export_onnx(str(ckpt), str(tmp_path / "m.onnx"))
    onnx_agent = make_agent(str(path))
    assert isinstance(onnx_agent, OnnxAgent)
    torch_agent = NetAgent(str(ckpt))

    game = Game(seed=5)
    spent = []
    while not game.is_over:
        obs, legal = game.observation(game.current), game.legal_actions()
        t0 = time.perf_counter()
        probs, value = onnx_agent.evaluate(obs, legal)
        spent.append(time.perf_counter() - t0)
        assert np.allclose(probs, torch_agent.probabilities(obs, legal), atol=1e-4)
        assert abs(sum(probs) - 1) < 1e-6
        game.step(onnx_agent.act(obs, legal))
    assert max(spent) < 1.0  # 出一手牌的延迟上限
    fresh = Game(seed=6)
    top = advise(onnx_agent, fresh.observation(fresh.current), fresh.legal_actions())
    assert 1 <= len(top["choices"]) <= 3

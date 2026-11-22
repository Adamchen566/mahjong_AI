"""日麻对局软件: RiichiMatch(一场半庄、局间暂停)和 /ws/riichi 全流程。"""
import json

import pytest
from fastapi.testclient import TestClient

from riichi import Action, ShantenAgent
from server import create_app
from server.riichi_match import RiichiMatch, insight


def play_out(match, agent, max_steps=20000):
    """用一个策略代替人,把整场打完;每局结束时检查暂停和结算,再继续。"""
    hands = 0
    steps = 0
    while not match.game.is_over:
        if match.paused:
            snap = match.snapshot()
            assert snap["view"]["result"] is not None and snap["view"]["legal"] == []
            assert not match.bot_step()  # 暂停时电脑不动
            match.resume()
            hands += 1
        elif match.waiting_for_human:
            view = match.snapshot()["view"]
            legal = [Action.from_id(a["id"]) for a in view["legal"]]
            assert legal
            match.human_action(agent.act(view, legal).id)
        else:
            assert match.bot_step()
        steps += 1
        assert steps < max_steps
    return hands


def test_match_plays_a_whole_hanchan(tmp_path):
    match = RiichiMatch(opponent="shanten", seed=5, records_dir=tmp_path)
    hands = play_out(match, ShantenAgent(0))
    snap = match.snapshot()
    assert snap["match"]["over"] and snap["view"]["final"]["ranks"]
    assert sum(snap["view"]["final"]["scores"]) == 100000
    assert hands == len(match.game.hand_results) - 1  # 最后一局结束直接是终局
    assert match.last_record and (tmp_path / match.last_record).is_file()


def test_snapshot_hides_other_hands_and_draws():
    match = RiichiMatch(opponent="simple", seed=6)
    while match.bot_to_act:
        match.bot_step()
    snap = match.snapshot()
    view = snap["view"]
    assert "hands" not in view
    for ev in match.game.events_for(0):
        if ev["type"] == "draw" and ev["seat"] != 0:
            assert ev["tile"] is None


def test_human_action_guards():
    match = RiichiMatch(opponent="simple", seed=7, human_seat=1)
    with pytest.raises(ValueError):
        match.human_action(0)  # 庄家是座位 0 的电脑,还没轮到人
    with pytest.raises(ValueError):
        RiichiMatch(opponent="nobody")


def test_chi_and_pon_options_carry_the_tiles_used():
    from riichi_helpers import position
    from riichi import actions as A
    from riichi.tiles import parse_tile
    from server.riichi_match import action_json

    g = position(["1347m258p369s1357z", "12m405m69p147s246z", "129m369p258s1357z", "369m147p258s1357z"], drawn="3m")
    g.step(A.discard(parse_tile("3m")))
    got = {a.id: action_json(g, a).get("uses") for a in g.legal_actions()}
    assert got[A.chi(0, False).id] == [parse_tile("4m"), parse_tile("5m")]
    assert got[A.chi(0, True).id] == [parse_tile("4m"), parse_tile("0m")]
    assert got[A.chi(2).id] == [parse_tile("1m"), parse_tile("2m")]


def test_insight_from_own_view():
    match = RiichiMatch(opponent="simple", seed=8)
    view = match.game.observation(0)  # 庄家刚配完牌,14 张
    tips = insight(view)
    assert tips is not None and "discards" in tips
    assert any(o["best"] for o in tips["discards"].values())


def test_websocket_flow(tmp_path):
    app = create_app(records_dir=tmp_path, dist_dir=tmp_path / "none", bot_delay=0, seed=11, advisor=None)
    client = TestClient(app)
    assert [o["id"] for o in client.get("/api/riichi/opponents").json()] == ["shanten", "simple"]
    agent = ShantenAgent(1)
    with client.websocket_connect("/ws/riichi") as ws:
        assert ws.receive_json()["match"] is None
        ws.send_text(json.dumps({"type": "new_match", "opponent": "shanten"}))
        state = ws.receive_json()
        hands = 0
        for _ in range(20000):
            m, view = state["match"], state["view"]
            if m["over"]:
                break
            if m["paused"]:
                ws.send_text(json.dumps({"type": "continue"}))
                hands += 1
            elif view["legal"]:
                legal = [Action.from_id(a["id"]) for a in view["legal"]]
                ws.send_text(json.dumps({"type": "action", "id": agent.act(view, legal).id}))
            # 一条请求之后服务端会推若干条 state(电脑每走一步一条),读到轮到人、暂停或结束为止
            while True:
                state = ws.receive_json()
                assert state["type"] == "state"
                m, view = state["match"], state["view"]
                if m["over"] or m["paused"] or view["legal"]:
                    break
        assert state["match"]["over"] and hands >= 1
        ws.send_text(json.dumps({"type": "action", "id": 0}))
        assert ws.receive_json()["type"] == "error"
        ws.receive_json()
        ws.send_text(json.dumps({"type": "quit_match"}))
        assert ws.receive_json()["match"] is None
    assert list((tmp_path / "riichi").glob("*.json"))
    assert client.get("/api/records").json() == []  # 日麻牌谱不混进川麻的牌谱列表

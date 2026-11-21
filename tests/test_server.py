import json

import pytest
from fastapi.testclient import TestClient

from chuanma import SimpleAgent
from chuanma.actions import Action
from server import Match, create_app
from server.match import list_records, load_record, record_steps, record_view


def play_human_with(match, agent):
    """用一个策略代替人,把当前这局打完。"""
    steps = 0
    while not match.game.is_over:
        if match.waiting_for_human:
            snap = match.snapshot()
            view = snap["view"]
            assert view["legal"], "轮到人时必须给出可选动作"
            legal = [Action.from_id(a["id"]) for a in view["legal"]]
            match.human_action(agent.act(view, legal).id)
        else:
            assert match.bot_step()
        steps += 1
        assert steps < 2000


# ---------------------------------------------------------------- Match


def test_match_plays_several_games_and_accumulates(tmp_path):
    match = Match(opponent="rule", seed=1, records_dir=tmp_path)
    agent = SimpleAgent()
    dealers = []
    running = [0, 0, 0, 0]
    for n in range(1, 4):
        match.start_game()
        dealers.append(match.game.dealer)
        assert match.game_no == n
        play_human_with(match, agent)
        running = [a + b for a, b in zip(running, match.game.scores)]
        assert match.totals == running
        assert sum(match.totals) == 0
        snap = match.snapshot()
        assert snap["view"]["phase"] == "END"
        assert "hands" in snap["view"] and "transfers" in snap["view"]
        assert snap["view"]["record"] == match.last_record
    assert dealers == [0, 1, 2]  # 轮庄
    assert len(list(tmp_path.glob("*.json"))) == 3


def test_match_guards():
    match = Match(opponent="simple", seed=2)
    match.start_game()
    with pytest.raises(RuntimeError):
        match.start_game()  # 上一局没打完
    while match.bot_to_act:
        match.bot_step()
    assert match.waiting_for_human
    assert not match.bot_step()
    with pytest.raises(ValueError):
        match.human_action(83)  # 开局不可能直接胡(HU 不在合法动作里)


def test_snapshot_never_leaks_other_hands():
    match = Match(opponent="rule", seed=3)
    match.start_game()
    agent = SimpleAgent()
    while not match.game.is_over:
        snap = match.snapshot()
        view = snap["view"]
        assert "hands" not in view
        assert view["hand"] == match.game.hand_tiles(0)
        for ev in snap["events"]:
            if ev["type"] == "draw" and ev["seat"] != 0:
                assert ev["tile"] is None
        if match.waiting_for_human:
            legal = [Action.from_id(a["id"]) for a in view["legal"]]
            match.human_action(agent.act(view, legal).id)
        else:
            match.bot_step()
    json.dumps(match.snapshot())  # 整个快照必须能序列化成 JSON


def test_snapshot_events_are_incremental():
    match = Match(opponent="simple", seed=4)
    match.start_game()
    first = match.snapshot()["events"]
    assert first and first[0]["type"] == "deal"
    assert match.snapshot()["events"] == []  # 没有新动作就没有新事件
    match.bot_step() if match.bot_to_act else match.human_action(match.snapshot()["view"]["legal"][0]["id"])
    total = len(match.game.events)
    again = match.snapshot()["events"]
    assert len(first) + len(again) == total


# ---------------------------------------------------------------- 牌谱


def test_record_replay_helpers(tmp_path):
    match = Match(opponent="simple", seed=5, records_dir=tmp_path)
    match.start_game()
    play_human_with(match, SimpleAgent())
    listing = list_records(tmp_path)
    assert len(listing) == 1 and listing[0]["scores"] == match.game.scores
    rec = load_record(tmp_path, listing[0]["name"])
    steps = record_steps(rec)
    assert len(steps) == len(rec.actions)
    assert all(set(s) == {"seat", "text"} for s in steps)
    start = record_view(rec, 0)
    assert [len(h) for h in start["hands"]] == [14, 13, 13, 13]
    end = record_view(rec, 10**6)  # 超出范围会被截到最后一步
    assert end["phase"] == "END" and end["scores"] == match.game.scores
    for bad in ["../secret.json", "nope.json", "a.txt"]:
        with pytest.raises(FileNotFoundError):
            load_record(tmp_path, bad)


# ---------------------------------------------------------------- HTTP / WebSocket


@pytest.fixture
def client(tmp_path):
    app = create_app(records_dir=tmp_path, dist_dir=tmp_path / "no-dist", bot_delay=0, seed=7)
    with TestClient(app) as c:
        yield c


def recv_until_my_turn_or_end(ws):
    while True:
        msg = ws.receive_json()
        assert msg["type"] == "state", msg
        view = msg["view"]
        if view and (view["legal"] or view["phase"] == "END"):
            return msg


def test_http_endpoints(client):
    assert [o["id"] for o in client.get("/api/opponents").json()] == ["rule", "simple"]
    assert client.get("/api/records").json() == []
    assert client.get("/api/records/nope.json").status_code == 404
    assert "还没有构建" in client.get("/").text


def test_websocket_full_game_then_next(client):
    agent = SimpleAgent()
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello == {"type": "state", "match": None, "view": None, "events": []}

        ws.send_json({"type": "new_match", "opponent": "rule"})
        msg = recv_until_my_turn_or_end(ws)
        assert msg["match"]["game_no"] == 1
        # 第一个决定是换三张: 一次提交三张
        view = msg["view"]
        assert view["phase"] == "EXCHANGE"
        suit = view["legal"][0]["tile"] // 9  # 能选的花色里至少有三张牌
        same_suit = [t for t in view["hand"] if t // 9 == suit][:3]
        picks = [88 + t for t in same_suit]  # 换三张动作的编号从 88 起
        ws.send_json({"type": "actions", "ids": picks})

        steps = 0
        while True:
            msg = recv_until_my_turn_or_end(ws)
            view = msg["view"]
            if view["phase"] == "END":
                break
            legal = [Action.from_id(a["id"]) for a in view["legal"]]
            ws.send_json({"type": "action", "id": agent.act(view, legal).id})
            steps += 1
            assert steps < 500
        assert sum(view["scores"]) == 0
        assert msg["match"]["totals"] == view["scores"]
        assert view["record"]

        ws.send_json({"type": "next_game"})
        msg = recv_until_my_turn_or_end(ws)
        assert msg["match"]["game_no"] == 2
        assert msg["view"]["dealer"] == 1

    # 牌谱接口能读到刚才那一局
    records = client.get("/api/records").json()
    assert len(records) == 1
    name = records[0]["name"]
    detail = client.get(f"/api/records/{name}").json()
    assert len(detail["steps"]) == records[0]["steps"]
    last = client.get(f"/api/records/{name}/view/{records[0]['steps']}").json()
    assert last["view"]["phase"] == "END"

    # 断线重连: 接着第二局,而不是回到开始页
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["match"]["game_no"] == 2 and msg["view"] is not None


def test_websocket_reports_errors_without_breaking(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "action", "id": 0})
        assert ws.receive_json()["type"] == "error"  # 还没开局
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"type": "new_match", "opponent": "nobody"})
        assert ws.receive_json()["type"] == "error"
        assert ws.receive_json()["match"] is None
        ws.send_json({"type": "new_match", "opponent": "simple"})
        msg = recv_until_my_turn_or_end(ws)
        ws.send_json({"type": "action", "id": 83})  # 现在不能胡
        assert ws.receive_json()["type"] == "error"
        assert ws.receive_json()["view"]["legal"] == msg["view"]["legal"]
        ws.send_json({"type": "quit_match"})
        assert ws.receive_json()["match"] is None

"""演示功能: 观战、思考可视化要用的数据、牌理接进对局、段位梯。"""
import json

import pytest
from fastapi.testclient import TestClient

from ai.ladder import play_deal, read_curve, summarize
from chuanma import GameRecord, SimpleAgent, play_game
from server import Match, create_app
from server.match import record_analysis, record_steps, record_view, spectate_record


class FixedAdvisor:
    """假模型: 最看好第一个合法动作,估值固定。"""

    def evaluate(self, obs, legal):
        n = len(legal)
        return ([0.7] + [0.3 / (n - 1)] * (n - 1) if n > 1 else [1.0]), 2.0


@pytest.fixture
def client(tmp_path):
    app = create_app(
        records_dir=tmp_path,
        dist_dir=tmp_path / "no-dist",
        bot_delay=0,
        seed=7,
        advisor=FixedAdvisor(),
        ladder_path=tmp_path / "ladder.json",
    )
    with TestClient(app) as c:
        yield c


def play_until_human(match):
    while match.bot_to_act:
        match.bot_step()


# ---------------------------------------------------------------- 牌理、概率条


def test_insight_and_tile_probabilities_reach_the_table():
    match = Match(opponent="simple", seed=3, advisor=FixedAdvisor())
    match.hint_on = True
    match.start_game()
    saw_insight = saw_bars = False
    for _ in range(300):
        play_until_human(match)
        if match.game.is_over:
            break
        snap = match.snapshot()
        view = snap["view"]
        legal = view["legal"]
        if view["phase"] in ("EXCHANGE", "CHOOSE_VOID"):
            assert "insight" not in view  # 还没开始打牌,没有牌理可说
        elif not view["won"][match.human_seat]:
            saw_insight = True
            tips = view["insight"]
            if view["phase"] == "TURN":
                # 每一张能打的牌都有评价,而且只评价能打的牌
                assert {o["tile"] for o in tips["discards"]} == {a["tile"] for a in legal if a["type"] == "DISCARD"}
        tiles = view["hint"]["tiles"]
        wanted = [a["tile"] for a in legal if a["type"] in ("DISCARD", "EXCHANGE")]
        assert [t for t, _ in tiles] == wanted
        saw_bars = saw_bars or bool(tiles)
        match.human_action(legal[0]["id"])
    assert match.game.is_over and saw_insight and saw_bars


# ---------------------------------------------------------------- 观战


def test_spectate_record_replays_to_the_same_result():
    record = spectate_record(["simple", "rule", "simple", "rule"], seed=11)
    assert record.meta["spectate"] and record.meta["agents"] == ["simple", "rule", "simple", "rule"]
    assert sum(record.scores) == 0
    view = record_view(record, len(record.actions))
    assert view["phase"] == "END" and view["scores"] == record.scores
    assert view["seat_labels"] == ["简单", "规则型", "简单", "规则型"]
    with pytest.raises(ValueError):
        spectate_record(["simple", "rule"])


def test_record_view_can_sit_at_any_seat_and_shows_every_shanten():
    record = spectate_record(["simple"] * 4, seed=5)
    middle = len(record.actions) // 2
    for seat in range(4):
        view = record_view(record, middle, seat)
        assert view["seat"] == seat and len(view["hands"]) == 4
        assert len(view["shanten"]) == 4
        for s, n in enumerate(view["shanten"]):
            assert (n is None) == view["won"][s]
    assert record_view(record, middle, 9)["seat"] == 0  # 乱给的座位号退回默认
    assert "seat_labels" not in record_view(GameRecord.from_game(play_game([SimpleAgent()] * 4, seed=1)), 0)


def test_steps_carry_what_the_sounds_need():
    record = spectate_record(["simple"] * 4, seed=5)
    steps = record_steps(record)
    kinds = {s["type"] for s in steps}
    assert {"EXCHANGE", "CHOOSE_VOID", "DISCARD"} <= kinds
    assert all(0 <= s["tile"] < 27 for s in steps if s["type"] == "DISCARD")


def test_analysis_has_a_value_for_every_step():
    record = spectate_record(["simple"] * 4, seed=5)
    result = record_analysis(record, FixedAdvisor())
    assert result["final"] == record.scores
    for row in result["steps"]:
        assert row["value"] == 2.0 and isinstance(row["score"], int)
        if not row["forced"]:
            assert 1 <= len(row["top"]) <= 3 and row["top"][0]["id"] == row["best"]["id"]
            assert all(0 <= p <= 1 for _, p in row["tiles"])
    # 四家都有自己的点,曲线才画得出四条
    last = {row["seat"]: row["score"] for row in result["steps"]}
    assert set(last) == {0, 1, 2, 3}


def test_spectate_over_http(client):
    bad = client.post("/api/spectate", json={"agents": ["simple", "nobody", "simple", "simple"]})
    assert bad.status_code == 400
    assert client.post("/api/spectate", json={"agents": ["simple"]}).status_code == 400

    made = client.post("/api/spectate", json={"agents": ["simple", "rule", "simple", "rule"], "seed": 3}).json()
    name = made["name"]
    detail = client.get(f"/api/records/{name}").json()
    assert detail["meta"]["spectate"] and len(detail["steps"]) == made["steps"]
    view = client.get(f"/api/records/{name}/view/40?seat=2").json()["view"]
    assert view["seat"] == 2 and view["seat_labels"][1] == "规则型"
    analysis = client.get(f"/api/records/{name}/analysis").json()
    assert analysis["available"] and len(analysis["steps"]) == made["steps"]
    # 观战的牌谱只在内存里,不写进牌谱目录,也不出现在牌谱列表里
    assert client.get("/api/records").json() == []


def test_spectate_keeps_only_recent_games(client):
    names = [client.post("/api/spectate", json={"agents": ["simple"] * 4, "seed": s}).json()["name"] for s in range(22)]
    assert len(set(names)) == 22
    assert client.get(f"/api/records/{names[0]}").status_code == 404
    assert client.get(f"/api/records/{names[-1]}").status_code == 200


# ---------------------------------------------------------------- 段位梯


def test_ladder_endpoint(client, tmp_path):
    assert client.get("/api/ladder").json()["available"] is False
    data = {"players": [{"id": "a", "label": "甲", "note": "", "games": None}], "matrix": [[None]], "games_per_pair": 8}
    (tmp_path / "ladder.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    got = client.get("/api/ladder").json()
    assert got["available"] and got["players"][0]["label"] == "甲"


def test_ladder_pairing_is_zero_sum_against_itself_and_favours_the_stronger():
    rows = [play_deal(("rule", "simple", seed)) for seed in range(40)]
    strong = summarize(rows)
    assert strong["lo"] <= strong["mean"] <= strong["hi"] and 0 <= strong["deal_in_rate"] <= 1
    weak = summarize([play_deal(("simple", "rule", seed)) for seed in range(40)])
    assert strong["mean"] > weak["mean"]
    # 同一个确定性策略自己对自己: 四个座位的得分加起来是 0
    same = [play_deal(("rule", "rule", seed))[0] for seed in range(5)]
    assert all(abs(x) < 1e-9 for x in same)


def test_read_curve_takes_only_evaluated_rows(tmp_path):
    log = tmp_path / "log.csv"
    log.write_text(
        "iteration,games,eval_score,eval_lo,eval_hi,eval_win_rate,eval_deal_in_rate\n"
        "1,100,,,,,\n"
        "2,200,0.5,0.1,0.9,0.7,0.45\n",
        encoding="utf-8",
    )
    assert read_curve(log) == [{"games": 200, "score": 0.5, "lo": 0.1, "hi": 0.9, "deal_in_rate": 0.45}]
    assert read_curve(tmp_path / "missing.csv") == []

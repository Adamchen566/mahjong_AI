import pytest

from chuanma.actions import HU, NUM_ACTIONS, PASS, Action, ActionType, discard
from chuanma.tiles import (
    counts_to_tiles,
    full_wall,
    make_tile,
    parse_tile,
    parse_tiles,
    rank_of,
    suit_of,
    tile_name,
    tile_str,
    tiles_str,
    tiles_to_counts,
)


def test_tile_encoding():
    assert make_tile(0, 1) == 0
    assert make_tile(2, 9) == 26
    for t in range(27):
        assert make_tile(suit_of(t), rank_of(t)) == t
        assert parse_tile(tile_str(t)) == t
    assert tile_str(13) == "5p"
    assert tile_name(13) == "5筒"


def test_parse_and_format():
    tiles = parse_tiles("123m 456p77s")
    assert tiles == [0, 1, 2, 12, 13, 14, 24, 24]
    assert tiles_str(tiles) == "123m456p77s"
    assert counts_to_tiles(tiles_to_counts(tiles)) == tiles


@pytest.mark.parametrize("bad", ["12", "m", "1x", "0m"])
def test_parse_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_tiles(bad)


def test_full_wall():
    wall = full_wall()
    assert len(wall) == 108
    assert tiles_to_counts(wall) == [4] * 27


def test_action_ids_round_trip():
    seen = set()
    for i in range(NUM_ACTIONS):
        a = Action.from_id(i)
        assert a.id == i
        seen.add(a)
    assert len(seen) == NUM_ACTIONS == 115
    assert discard(5).id == 5
    assert HU.id == 83 and PASS.id == 84
    assert Action.from_id(85) == Action(ActionType.CHOOSE_VOID, 0)
    with pytest.raises(ValueError):
        Action.from_id(NUM_ACTIONS)

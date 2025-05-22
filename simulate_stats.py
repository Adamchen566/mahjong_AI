from collections import defaultdict
from game_chuan import WindPosition, MahjongBoard
from agents.koutsu import KoutsuAI
from core.rules import *
from core.display import format_pos_name
import sys
import contextlib

NUM_SIMULATIONS = 1000
positions = list(WindPosition)

win_count = defaultdict(int)
meld_count = defaultdict(int)

# 防止每一局都输出，重定向stdout
@contextlib.contextmanager
def suppress_output():
    with open('nul', 'w') as fnull:
        old_stdout = sys.stdout
        sys.stdout = fnull
        try:
            yield
        finally:
            sys.stdout = old_stdout

def simulate_game():
    board = MahjongBoard(rule="chuan")
    board.shuffle_and_deal()
    board.sort_all_hands()

    agents = {
        WindPosition.EAST: KoutsuAI(WindPosition.EAST, board),
        WindPosition.SOUTH: KoutsuAI(WindPosition.SOUTH, board),
        WindPosition.WEST: KoutsuAI(WindPosition.WEST, board),
        WindPosition.NORTH: KoutsuAI(WindPosition.NORTH, board),
    }

    finished = set()
    current_pos = WindPosition.EAST
    discard = agents[current_pos].choose_discard()
    board.discard_tile(current_pos, discard)
    current_pos = current_pos.next()

    while not board.is_draw():
        if current_pos in finished:
            current_pos = current_pos.next()
            continue

        try:
            drawn = board.draw_tile(current_pos)
        except:
            break
        board.sort_hand(current_pos)

        hand = board.get_hand(current_pos)
        melds = board.get_melds(current_pos)
        if can_win_standard(hand, melds):
            if agents[current_pos].decide_win():
                finished.add(current_pos)
                continue

        # 杠（略去副露处理逻辑，只计数）
        kan_type, kan_tile = agents[current_pos].decide_concealed_or_added_kan()
        if kan_type and kan_tile:
            board.add_meld(current_pos, [kan_tile]*4)

        discard = agents[current_pos].choose_discard()
        board.discard_tile(current_pos, discard)
        current_pos = current_pos.next()

    result = {}
    for pos in positions:
        result[pos] = {
            "win": pos in finished,
            "meld": len(board.get_melds(pos))
        }
    return result

# 主运行入口
if __name__ == "__main__":
    for i in range(NUM_SIMULATIONS):
        with suppress_output():
            result = simulate_game()
        for pos in positions:
            if result[pos]["win"]:
                win_count[pos] += 1
            if result[pos]["meld"] > 0:
                meld_count[pos] += 1

    print("====== 统计结果 ======")
    for pos in positions:
        print(f"{format_pos_name(pos)}: 胡牌率 = {win_count[pos] / NUM_SIMULATIONS:.2%}，副露率 = {meld_count[pos] / NUM_SIMULATIONS:.2%}")

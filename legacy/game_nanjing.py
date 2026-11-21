from core.board import MahjongBoard
from core.player import WindPosition
from agents.simple import SimpleAI
from core.display import color_tile, print_full_state

def check_pon_or_kan(board, last_tile, last_pos, agents):
    for i in range(1, 4):
        responder_pos = WindPosition((last_pos.value - i) % 4)
        agent = agents[responder_pos]

        if agent.can_win_on_tile(last_tile):
            if agent.decide_win(last_tile):
                print(f"{responder_pos.name} 胡了 {last_tile}（荣和）！")
                return "win", responder_pos, last_tile

        action = agent.decide_meld_action(last_tile)
        if action == 'kan':
            board.remove_tiles(responder_pos, [last_tile]*3)
            board.add_meld(responder_pos, [last_tile]*4)
            print(f"{responder_pos.name} 杠了 {last_tile}")
            return "meld", responder_pos, last_tile

        elif action == 'pon':
            board.remove_tiles(responder_pos, [last_tile]*2)
            board.add_meld(responder_pos, [last_tile]*3)
            print(f"{responder_pos.name} 碰了 {last_tile}")
            return "meld", responder_pos, last_tile

    return False, last_pos, last_tile

def main():
    board = MahjongBoard(rule="nanjing")
    board.shuffle_and_deal()
    board.sort_all_hands()

    print("\n============================ 开局初始牌面（东家14张） ============================")
    print_full_state(board)

    agents = {
        WindPosition.EAST: SimpleAI(WindPosition.EAST, board),
        WindPosition.SOUTH: SimpleAI(WindPosition.SOUTH, board),
        WindPosition.WEST: SimpleAI(WindPosition.WEST, board),
        WindPosition.NORTH: SimpleAI(WindPosition.NORTH, board),
    }

    round_counter = 1
    first_discard = agents[WindPosition.EAST].choose_discard()
    board.discard_tile(WindPosition.EAST, first_discard)
    print(f"\n【{WindPosition.EAST.name} 首轮打出】: {first_discard}")

    current_pos = WindPosition.EAST.next()
    last_tile = first_discard

    while not board.is_draw():
        if current_pos == WindPosition.EAST:
            print(f"\n========== 第 {round_counter} 回合 ==========")
            round_counter += 1

        drawn = board.draw_tile(current_pos)
        print(f"{current_pos.name} 摸牌: {drawn}")
        board.sort_hand(current_pos)

        if agents[current_pos].can_win():
            if agents[current_pos].decide_win():
                print(f"{current_pos.name} 自摸胡了！（南京结束）")
                break

        discard = agents[current_pos].choose_discard()
        board.discard_tile(current_pos, discard)
        print(f"{current_pos.name} 打出: {discard}")

        result = check_pon_or_kan(board, discard, current_pos, agents)
        if isinstance(result, tuple) and result[0] == "win":
            _, winner_pos, _ = result
            print(f"{winner_pos.name} 荣和胡牌，游戏结束（南京）")
            break

        if isinstance(result, tuple) and result[0] == "meld":
            current_pos = result[1].next()
            print_full_state(board)
            continue

        current_pos = current_pos.next()
        print_full_state(board)

    print("\n============================= 游戏结束（南京） =============================")

if __name__ == "__main__":
    main()
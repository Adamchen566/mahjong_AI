from core.board import MahjongBoard
from core.player import WindPosition
from agents.human import HumanAgent
from agents.simple import SimpleAI
from agents.koutsu import KoutsuAI, can_win_koutsu_style
from display import print_full_state, format_pos_name, color_tile

focus_pos = WindPosition.EAST

def check_pon_or_kan(board, last_tile, last_pos, agents):
    for offset in range(1, 4):  # 逆时针三家
        responder_pos = WindPosition((last_pos.value - offset) % 4)
        agent = agents[responder_pos]

        # ✅ 先检查是否能荣和
        hand = board.get_hand(responder_pos)
        melds = board.get_melds(responder_pos)
        if can_win_koutsu_style(hand, melds, last_tile):
            if agent.decide_win(last_tile):
                print(f"🎉🎉🎉 {format_pos_name(responder_pos)} 胡了 {color_tile(last_tile)}（荣和）！ 🎉🎉🎉")
                board.add_meld(responder_pos, [last_tile])
                return "win", responder_pos, last_tile

        # 再处理碰或杠
        action = agent.decide_meld_action(last_tile)
        can_gang = len(board.wall) > 1
        if can_gang and action == 'kan':
            if action == 'kan':
                board.remove_tiles(responder_pos, [last_tile] * 3)
                board.add_meld(responder_pos, [last_tile] * 4)
                print(f"{format_pos_name(responder_pos)} 杠了 {color_tile(last_tile)}")

                # 杠完摸一张
                drawn = board.draw_tile(responder_pos)
                if responder_pos == focus_pos:
                    print(f"{format_pos_name(responder_pos)} 杠后摸牌: {color_tile(drawn)}")
                board.sort_hand(responder_pos)

                # 胡牌检查
                if agent.can_win():
                    if agent.decide_win():
                        print(f"🎉🎉🎉 {format_pos_name(responder_pos)} 杠后自摸胡了！ 🎉🎉🎉")
                        board.add_meld(responder_pos, [last_tile])
                        return "win", responder_pos, drawn

                # 打一张
                discard = agent.choose_discard()
                board.discard_tile(responder_pos, discard)
                print(f"{format_pos_name(responder_pos)} 打出: {color_tile(discard)}")
                return "meld", responder_pos.next(), discard

        elif action == 'pon':
            board.remove_tiles(responder_pos, [last_tile] * 2)
            board.add_meld(responder_pos, [last_tile] * 3)
            discard = agent.choose_discard()
            board.discard_tile(responder_pos, discard)
            print(f"{format_pos_name(responder_pos)} 碰了 {color_tile(last_tile)} 并打出: {color_tile(discard)}")
            return "meld", responder_pos.next(), discard

    return False, last_pos, last_tile


def main():
    focus_pos = WindPosition.EAST  # 👈 只观察东家
    board = MahjongBoard(rule="chuan")
    board.shuffle_and_deal()
    board.sort_all_hands()

    print("\n============================ 开局初始牌面（东家14张） ============================")
    print_full_state(board)

    agents = {
        WindPosition.EAST: HumanAgent(WindPosition.EAST, board),
        WindPosition.SOUTH: KoutsuAI(WindPosition.SOUTH, board),
        WindPosition.WEST: KoutsuAI(WindPosition.WEST, board),
        WindPosition.NORTH: KoutsuAI(WindPosition.NORTH, board),
    }

    finished_players = set()
    round_counter = 1
    dealer = WindPosition.EAST

    first_discard = agents[dealer].choose_discard()
    board.discard_tile(dealer, first_discard)
    print(f"\n【{format_pos_name(WindPosition.EAST)} 首轮打出】: {color_tile(first_discard)}")
    print(f"剩余牌数: {len(board.wall)}")

    current_pos = dealer.next()
    while current_pos in finished_players:
        current_pos = current_pos.next()

    last_tile = first_discard
    last_round_starter = dealer

    while not board.is_draw():
        if current_pos == last_round_starter:
            print(f"\n================================ 第 {round_counter} 回合 ===============================")
            round_counter += 1
            last_round_starter = None  # 清除当前起始者标记

        drawn = board.draw_tile(current_pos)
        print(f"{format_pos_name(current_pos)} 摸牌: {color_tile(drawn)}")
        print(f"剩余牌数: {len(board.wall)}")
        board.sort_hand(current_pos)

        hand = board.get_hand(current_pos)
        melds = board.get_melds(current_pos)

        # 摸完决定是否杠（暗杠/加杠）# ✅ 仅在有牌可摸的情况下允许杠
        can_gang = len(board.wall) > 1
        kan_type, kan_tile = (None, None)
        if can_gang:
            kan_type, kan_tile = agents[current_pos].decide_concealed_or_added_kan()
        if kan_type == "ankan" and kan_tile is not None:
            board.remove_tiles(current_pos, [kan_tile] * 4)
            board.add_meld(current_pos, [kan_tile] * 4)
            print(f"{format_pos_name(current_pos)} 暗杠了 {color_tile(kan_tile)}")

        elif kan_type == "chakan" and kan_tile is not None:
            board.remove_tiles(current_pos, [kan_tile])
            for meld in board.get_melds(current_pos):
                if len(meld) == 3 and all(tile == kan_tile for tile in meld):
                    meld.append(kan_tile)
                    break
            print(f"{format_pos_name(current_pos)} 加杠了 {color_tile(kan_tile)}")
        else:
            kan_tile = None

        if kan_type:
            drawn = board.draw_tile(current_pos)
            print(f"{format_pos_name(current_pos)} 杠后摸牌: {color_tile(drawn)}")
            board.sort_hand(current_pos)

            hand = board.get_hand(current_pos)
            melds = board.get_melds(current_pos)
            if can_win_koutsu_style(hand, melds):
                if agents[current_pos].decide_win():
                    print(f"🎉🎉🎉 {format_pos_name(current_pos)} 杠后自摸胡了！ 🎉🎉🎉")
                    board.add_meld(current_pos, [drawn])
                    finished_players.add(current_pos)
                    if len(finished_players) >= 3:
                        print("三家胡牌，游戏结束。")
                        return
                    current_pos = current_pos.next()
                    last_round_starter = current_pos
                    continue

        if can_win_koutsu_style(hand, melds):
            if agents[current_pos].decide_win(drawn):
                print(f"🎉🎉🎉 {format_pos_name(current_pos)} 自摸胡了！ 🎉🎉🎉")
                board.add_meld(current_pos, [drawn])
                finished_players.add(current_pos)
                if len(finished_players) >= 3:
                    print("三家胡牌，游戏结束。")
                    return
                current_pos = current_pos.next()
                last_round_starter = current_pos  # 胡完由下家开始新回合
                continue

            discard = agents[current_pos].choose_discard(drawn)
            board.discard_tile(current_pos, discard)
            print(f"{format_pos_name(current_pos)} 打出: {color_tile(discard)}")

            result = check_pon_or_kan(board, discard, current_pos, agents)
            if result and result[0] == "win":
                finished_players.add(result[1])
                if len(finished_players) >= 3:
                    print("三家胡牌，游戏结束。")
                    return
                current_pos = result[1].next()
                last_round_starter = current_pos
                continue
            elif result and result[0] == "meld":
                current_pos = result[1]
                last_round_starter = current_pos
                print_full_state(board)
                continue

        discard = agents[current_pos].choose_discard()
        board.discard_tile(current_pos, discard)
        print(f"{format_pos_name(current_pos)} 打出: {color_tile(discard)}")
        print_full_state(board)
        print("\n")

        result = check_pon_or_kan(board, discard, current_pos, agents)
        if isinstance(result, tuple) and result[0] == "win":
            _, winner_pos, _ = result
            finished_players.add(winner_pos)
            if len(finished_players) >= 3:
                print("三家胡牌，游戏结束。")
                break
            current_pos = winner_pos.next()
            last_round_starter = current_pos
            continue

        if isinstance(result, tuple) and result[0] == "meld":
            current_pos = result[1]
            last_round_starter = current_pos  # 副露后从其下家作为新一轮起点
            print_full_state(board)
            continue
        _, _, discard = result
        if last_round_starter is None:
            last_round_starter = current_pos  # 普通摸打的起始者

        current_pos = current_pos.next()
        continue

    print("\n============================= 游戏结束（川麻） =============================")
    print("所有玩家的手牌：")
    print_full_state(board)
    print("胡牌玩家有：")
    for pos in finished_players:
        print(f"  - {format_pos_name(pos)}")
    print("\n所有玩家的弃牌：")
    for pos in WindPosition:
        discards = board.get_discards(pos)
        if discards:
            colored_discards = ' '.join([color_tile(t) for t in discards])
            print(f"{format_pos_name(pos)} 弃牌: {colored_discards}")
        else:
            print(f"{format_pos_name(pos)} 弃牌: 无")

if __name__ == "__main__":
    main()
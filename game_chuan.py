from core.board import MahjongBoard
from core.player import WindPosition
from core.display import *
from core.rules import *
from core.tiles import Tile
from agents.human import HumanAgent
from agents.koutsu import KoutsuAI
import json

focus_pos = WindPosition.EAST


def main():
    focus_pos = WindPosition.EAST  # 👈 只观察东家
    board = MahjongBoard(rule="chuan")
    board.shuffle_and_deal()

    # 👇 读取东家的手牌替换
    try:
        east_hand = load_east_hand_from_vision("east_hand.json")
        board.hands[WindPosition.EAST] = east_hand
        print(f"东家手牌已由摄像头识别结果替换: {east_hand}")
    except Exception as e:
        print("无法读取摄像头识别的手牌，使用默认发牌。", e)

    board.sort_all_hands()

    print("\n============================ 开局初始牌面（东家14张） ============================")
    # 指定玩家\AI
    agents = {
        WindPosition.EAST: HumanAgent(WindPosition.EAST, board),
        WindPosition.SOUTH: KoutsuAI(WindPosition.SOUTH, board),
        WindPosition.WEST: KoutsuAI(WindPosition.WEST, board),
        WindPosition.NORTH: KoutsuAI(WindPosition.NORTH, board),
    }
    print_full_state(board, agents) # 打印初始牌面

    finished_players = set()    # 记录胡牌玩家
    round_counter = 1           # 回合计数器
    dealer = WindPosition.EAST  # 东家先手

    # 换三张
    tiles_to_give = {} # 给每家换出的牌
    for pos in WindPosition:
        sel = agents[pos].select_three_exchange()   # List[Tile], 长度一定是 3
        for t in sel:
            board.get_hand(pos).remove(t)           # 先从手上移除
        tiles_to_give[pos] = sel
    
    exchange_direction = determine_exchange_direction() # 换牌方向
    exchange_three_tiles(board, tiles_to_give, exchange_direction)
    board.sort_all_hands()
    print_full_state(board, agents)  # 显示换牌后的牌面

    # 定缺
    dingque_phase(board, agents)

    # 查天胡
    hand = board.get_hand(dealer)
    melds = board.get_melds(dealer)
    print(f"\n检查{format_pos_name(dealer)}是否天胡, 缺门是{agents[dealer].missing_suit}")
    if can_win_standard(hand, melds):
        if agents[dealer].decide_win(None):
            print(f"🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉 {format_pos_name(dealer)} 天胡了！ 🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
            finished_players.add(dealer)
            current_pos = pos.next()
            last_round_starter = current_pos

    # 庄家丢第一张牌
    first_discard = agents[dealer].choose_discard()
    board.discard_tile(dealer, first_discard)
    print(f"\n【{format_pos_name(WindPosition.EAST)} 首轮打出】: {color_tile(first_discard)}")
    print(f"剩余牌数: {len(board.wall)}")

    # 检查第一张是否是胡牌
    for dihu_pos in WindPosition:
        if dihu_pos == dealer:
            continue
        print(f"检查 {format_pos_name(dihu_pos)} 是否地胡 {color_tile(first_discard)}")
        if can_win_standard(board.get_hand(dihu_pos), board.get_melds(dihu_pos), first_discard):
            if agents[dihu_pos].decide_win(first_discard):
                print(f"🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉 {format_pos_name(dihu_pos)} 地胡了！ 🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
                board.add_meld(dihu_pos, [first_discard])
                finished_players.add(dihu_pos)
                current_pos = dihu_pos.next()
                last_round_starter = dihu_pos  # 胡完由下家开始新回合

    current_pos = dealer.next()
    while current_pos in finished_players:
        current_pos = current_pos.next()
    last_tile = first_discard
    last_round_starter = dealer

    while not board.is_draw():
        # 跳过已经胡牌的玩家
        if current_pos in finished_players:
            current_pos = current_pos.next()
            continue

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
            if agents[current_pos].can_win_on_tile(drawn):
                if agents[current_pos].decide_win(drawn):
                    board.add_meld(current_pos, [drawn])
                    finished_players.add(current_pos)
                    print(f"🎉🎉🎉 {format_pos_name(current_pos)} 杠后自摸胡了！ 🎉🎉🎉")
                    board.add_meld(current_pos, [drawn])
                    finished_players.add(current_pos)
                    if len(finished_players) >= 3:
                        print("三家胡牌，游戏结束。")
                        return
                    current_pos = current_pos.next()
                    last_round_starter = current_pos
                    continue

        
            
            # 如果不胡牌，继续丢牌
            discard = agents[current_pos].choose_discard()
            board.discard_tile(current_pos, discard)
            print(f"{format_pos_name(current_pos)} 打出: {color_tile(discard)}")

            # 检查其他三家是否能碰杠或胡
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
                print_full_state(board, agents)
                continue

        # 检查是否能自摸
        print(f"{format_pos_name(current_pos)}检查是否自摸")
        if can_win_standard(board.get_hand(current_pos), board.get_melds(current_pos)):
            if agents[current_pos].decide_win(drawn):
                print(f"🎉🎉🎉🎉🎉🎉 {format_pos_name(current_pos)} 自摸胡了！ 🎉🎉🎉🎉🎉🎉")
                board.add_meld(current_pos, [drawn])
                finished_players.add(current_pos)
                if len(finished_players) >= 3:
                    print("三家胡牌，游戏结束。")
                    return
                current_pos = current_pos.next()
                last_round_starter = current_pos  # 胡完由下家开始新回合
                continue

        # 如果不胡牌，继续丢牌
        discard = agents[current_pos].choose_discard()
        board.discard_tile(current_pos, discard)
        print(f"{format_pos_name(current_pos)} 打出: {color_tile(discard)}")
        print_full_state(board, agents)
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
            print_full_state(board, agents)
            continue
        _, _, discard = result
        if last_round_starter is None:
            last_round_starter = current_pos  # 普通摸打的起始者

        current_pos = current_pos.next()
        continue

    print("\n============================= 游戏结束（川麻） =============================")
    print("所有玩家的手牌：")
    print_full_state(board, agents)
    print("胡牌玩家有：")
    for pos in finished_players:
        print(f"  - {format_pos_name(pos)}")
    print("\n所有玩家的弃牌：")
    for pos in WindPosition:
        discards = board.get_discards(pos)
        if discards:
            colored_discards = ' '.join([color_tile(t) for t in discards])
            board.sort_hand(pos)
            print(f"{format_pos_name(pos)} 弃牌: {colored_discards}")
        else:
            print(f"{format_pos_name(pos)} 弃牌: 无")

if __name__ == "__main__":
    main()
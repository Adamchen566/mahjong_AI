from core.board import MahjongBoard
from core.player import WindPosition
from core.display import *
from core.rules import *
from core.score import *
from core.fan import get_fan_score
from agents.human import HumanAgent
from agents.koutsu import KoutsuAI
from agents.oracle import OracleAI

focus_pos = WindPosition.EAST
recorder = ScoreRecorder("score_log.json")
recorder.load()  # 启动时读取历史数据

def main():
    game_over = False
    win_records = []  # 记录所有胡牌信息
    board = MahjongBoard(rule="chuan")
    board.shuffle_and_deal()
    board.sort_all_hands()

    print("\n============================ 开局初始牌面（东家14张） ============================")
    agents = {
        WindPosition.EAST: HumanAgent(WindPosition.EAST, board, None),
        WindPosition.SOUTH: OracleAI(WindPosition.SOUTH, board),
        WindPosition.WEST: KoutsuAI(WindPosition.WEST, board),
        WindPosition.NORTH: KoutsuAI(WindPosition.NORTH, board),
    }
    scores = {pos: 0 for pos in WindPosition}
    score_logs = {pos: [] for pos in WindPosition}
    print_full_state(board, agents)  # 打印初始牌面

    finished_players = set()
    round_counter = 1
    dealer = WindPosition.EAST

    # 换三张
    tiles_to_give = {}
    for pos in WindPosition:
        sel = agents[pos].select_three_exchange()
        for t in sel:
            board.get_hand(pos).remove(t)
        tiles_to_give[pos] = sel

    exchange_direction = determine_exchange_direction()
    exchange_three_tiles(board, tiles_to_give, exchange_direction)
    board.sort_all_hands()
    print_full_state(board, agents)

    # 定缺
    dingque_phase(board, agents)

    # 查天胡
    hand = board.get_hand(dealer)
    melds = board.get_melds(dealer)
    print(f"\n检查{format_pos_name(dealer)}是否天胡, 缺门是{agents[dealer].missing_suit}")
    tianhu = dihu = False
    first_discard = None
    if can_win_all(hand, melds):
        if agents[dealer].decide_win(None):
            print(f"🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉 {format_pos_name(dealer)} 天胡了！ 🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
            finished_players.add(dealer)
            current_pos = dealer.next()
            last_round_starter = current_pos
            tianhu = True
            win_records.append({'pos': dealer, 'type': 'zimo', 'loser': None})
        else:
            current_pos = dealer.next()
            last_round_starter = dealer
    else:
        current_pos = dealer.next()
        last_round_starter = dealer

    # 未天胡,庄家打牌
    if (not tianhu):
        print_seen_matrix_chuan(board, agents, "庄家打牌前 见牌矩阵")
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
            if can_win_all(board.get_hand(dihu_pos), board.get_melds(dihu_pos), first_discard):
                if agents[dihu_pos].decide_win(first_discard):
                    print(f"🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉 {format_pos_name(dihu_pos)} 地胡了！ 🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
                    board.add_meld(dihu_pos, [first_discard])
                    finished_players.add(dihu_pos)
                    current_pos = dihu_pos.next()
                    last_round_starter = dihu_pos
                    dihu = True
                    win_records.append({'pos': dihu_pos, 'type': 'ron', 'loser': dealer})

    # 跳过已胡玩家
    while current_pos in finished_players:
        current_pos = current_pos.next()
    last_tile = first_discard

    while not board.is_draw():
        if current_pos in finished_players:
            current_pos = current_pos.next()
            continue

        if current_pos == last_round_starter:
            print(f"\n================================ 第 {round_counter} 回合 ===============================")
            round_counter += 1
            last_round_starter = None

        # 摸牌
        drawn = drawn = board.draw_tile(current_pos)
        print(f"{format_pos_name(current_pos)} 摸牌: {color_tile(drawn)}")
        print(f"剩余牌数: {len(board.wall)}")
        board.sort_hand(current_pos)
        print_seen_matrix_chuan(board, agents, f"{format_pos_name(current_pos)}摸牌后 见牌矩阵")

        hand = board.get_hand(current_pos)
        melds = board.get_melds(current_pos)

        # 摸完决定是否杠
        can_gang = len(board.wall) > 1
        kan_type, kan_tile = (None, None)
        if can_gang and hasattr(agents[current_pos], "decide_concealed_or_added_kan"):
            kan_type, kan_tile = agents[current_pos].decide_concealed_or_added_kan()

        if kan_type == "ankan" and kan_tile is not None:
            hand_count = board.get_hand(current_pos).count(kan_tile)
            if hand_count >= 4:
                board.remove_tiles(current_pos, [kan_tile] * 4)
                board.add_meld(current_pos, [kan_tile] * 4)
                print(f"{format_pos_name(current_pos)} 暗杠了 {color_tile(kan_tile)}")
            else:
                print(f"[警告] {format_pos_name(current_pos)} 尝试暗杠 {color_tile(kan_tile)} 但手牌不足4张，跳过！")
        elif kan_type == "chakan" and kan_tile is not None:
            has_koutsu = any(len(meld) == 3 and all(tile == kan_tile for tile in meld) for meld in board.get_melds(current_pos))
            hand_count = board.get_hand(current_pos).count(kan_tile)
            if has_koutsu and hand_count >= 1:
                board.remove_tiles(current_pos, [kan_tile])
                for meld in board.get_melds(current_pos):
                    if len(meld) == 3 and all(tile == kan_tile for tile in meld):
                        meld.append(kan_tile)
                        break
                print(f"{format_pos_name(current_pos)} 加杠了 {color_tile(kan_tile)}")
                # ----------- 加杠成功才摸牌 -------------
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
                        win_records.append({'pos': current_pos, 'type': 'zimo', 'loser': None})
                        if len(finished_players) >= 3:
                            print("三家胡牌，游戏结束。")
                            game_over = True
                            break
                        current_pos = current_pos.next()
                        last_round_starter = current_pos
                        continue
                # 否则正常出牌
                discard = agents[current_pos].choose_discard()
                board.discard_tile(current_pos, discard)
                print(f"{format_pos_name(current_pos)} 打出: {color_tile(discard)}")
                result = check_pon_or_kan(board, discard, current_pos, agents, finished_players)
                if result and result[0] == "win":
                    finished_players.add(result[1])
                    win_records.append({'pos': winner_pos, 'type': 'ron', 'loser': current_pos})
                    print(f"🎉🎉🎉 {format_pos_name(result[1])} 荣胡了！ 🎉🎉🎉")
                    if len(finished_players) >= 3:
                        print("三家胡牌，游戏结束。")
                        game_over = True
                        break
                    current_pos = result[1].next()
                    last_round_starter = current_pos
                    continue
                elif result and result[0] == "meld":
                    current_pos = result[1]
                    last_round_starter = current_pos
                    print_full_state(board, agents)
                    continue
                # ----------- 加杠失败后直接打牌 -------------
            else:
                print(f"[警告] {format_pos_name(current_pos)} 尝试加杠 {color_tile(kan_tile)} 失败，刻子或手牌数量不符，跳过！")
                # 加杠失败不摸牌，直接进入打牌环节
                discard = agents[current_pos].choose_discard()
                board.discard_tile(current_pos, discard)
                print(f"{format_pos_name(current_pos)} 打出: {color_tile(discard)}")
                print_full_state(board, agents)
                print("\n")
                result = check_pon_or_kan(board, discard, current_pos, agents, finished_players)
                if result and result[0] == "win":
                    finished_players.add(result[1])
                    win_records.append({'pos': winner_pos, 'type': 'ron', 'loser': current_pos})
                    print(f"🎉🎉🎉 {format_pos_name(result[1])} 荣胡了！ 🎉🎉🎉")
                    if len(finished_players) >= 3:
                        print("三家胡牌，游戏结束。")
                        game_over = True
                        break
                    current_pos = result[1].next()
                    last_round_starter = current_pos
                    continue
                elif result and result[0] == "meld":
                    current_pos = result[1]
                    last_round_starter = current_pos
                    print_full_state(board, agents)
                    continue
                # 若没被碰杠等，正常到下一家
                current_pos = current_pos.next()
                continue

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
                    win_records.append({'pos': current_pos, 'type': 'zimo', 'loser': None})
                    print(f"🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉 {format_pos_name(current_pos)} 杠后自摸胡了！ 🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
                    if len(finished_players) >= 3:
                        print("三家胡牌，游戏结束。")
                        return
                    current_pos = current_pos.next()
                    last_round_starter = current_pos
                    continue
            discard = agents[current_pos].choose_discard()
            board.discard_tile(current_pos, discard)
            print(f"{format_pos_name(current_pos)} 打出: {color_tile(discard)}")
            result = check_pon_or_kan(board, discard, current_pos, agents, finished_players)
            if result and result[0] == "win":
                finished_players.add(result[1])
                win_records.append({'pos': winner_pos, 'type': 'ron', 'loser': current_pos})
                print(f"🎉🎉🎉 {format_pos_name(result[1])} 荣胡了！ 🎉🎉🎉")
                if len(finished_players) >= 3:
                    print("三家胡牌，游戏结束。")
                    game_over = True
                    break
                current_pos = result[1].next()
                last_round_starter = current_pos
                continue
            elif result and result[0] == "meld":
                current_pos = result[1]
                last_round_starter = current_pos
                print_full_state(board, agents)
                continue

        # 检查是否自摸
        print(f"{format_pos_name(current_pos)}检查是否自摸")
        if can_win_all(board.get_hand(current_pos), board.get_melds(current_pos), drawn):
            if agents[current_pos].decide_win(drawn):
                print(f"🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉 {format_pos_name(current_pos)} 自摸胡了！ 🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")
                board.add_meld(current_pos, [drawn])
                finished_players.add(current_pos)
                win_records.append({'pos': current_pos, 'type': 'zimo', 'loser': None})
                if len(finished_players) >= 3:
                    print("三家胡牌，游戏结束。")
                    game_over = True
                    break
                current_pos = current_pos.next()
                last_round_starter = current_pos
                continue

        # 不胡牌，打牌
        discard = agents[current_pos].choose_discard()
        board.discard_tile(current_pos, discard)
        print(f"{format_pos_name(current_pos)} 打出: {color_tile(discard)}")
        print_full_state(board, agents)
        print("\n")

        result = check_pon_or_kan(board, discard, current_pos, agents, finished_players)
        if isinstance(result, tuple) and result[0] == "win":
            _, winner_pos, _ = result
            finished_players.add(winner_pos)
            win_records.append({'pos': winner_pos, 'type': 'ron', 'loser': current_pos})
            print(f"🎉🎉🎉 {format_pos_name(winner_pos)} 荣胡了！ 🎉🎉🎉")
            if len(finished_players) >= 3:
                print("三家胡牌，游戏结束。")
                game_over = True
                break
            current_pos = winner_pos.next()
            last_round_starter = current_pos
            continue
        if isinstance(result, tuple) and result[0] == "meld":
            current_pos = result[1]
            last_round_starter = current_pos
            print_full_state(board, agents)
            continue
        _, _, discard = result
        if last_round_starter is None:
            last_round_starter = current_pos
        current_pos = current_pos.next()
        continue

    print("\n============================= 游戏结束（川麻） =============================")
    print("所有玩家的手牌：")
    print_full_state(board, agents)
    print("胡牌玩家有：")
    for rec in win_records:
        pos = rec['pos']
        win_type = rec['type']
        loser_pos = rec['loser']
        hand = board.get_hand(pos)
        melds = board.get_melds(pos)
        # 是否天胡、地胡可继续判断
        if tianhu and pos == dealer:
            score, fans = get_fan_score(hand, melds, is_tianhu=True)
        elif dihu and pos != dealer:
            score, fans = get_fan_score(hand, melds, is_dihu=True)
        else:
            score, fans = get_fan_score(hand, melds)
        # 结算分数
        settle_results = settle_scores(
            scores, pos, win_type, score, loser_pos=loser_pos, finished_players=finished_players
        )
        score_logs[pos].append({
            "fans": fans,
            "score": score,
            "tile": [str(t) for t in hand],
            "melds": [[str(t) for t in meld] for meld in melds],
            "type": "自摸" if win_type=="zimo" else "荣胡",
            "stage": round_counter
        })
        print(f"{format_pos_name(pos)} {'自摸' if win_type=='zimo' else '荣胡'}获得 {score} 分，番型：{'/'.join(fans)}")
        for p, delta in settle_results:
            if delta > 0:
                print(f"{format_pos_name(p)} 获得 {delta} 分")
            else:
                print(f"{format_pos_name(p)} 失去 {-delta} 分")

    recorder.record_game(scores, score_logs)
    recorder.save()

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
    for i in range(2):
        result = main()
    recorder.print_summary()
    print("累计总分:", recorder.get_total_scores())




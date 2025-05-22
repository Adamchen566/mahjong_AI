from core.board import MahjongBoard
from core.player import WindPosition
from core.board import Tile
from agents.human import HumanAgent
from agents.simple import SimpleAI
import random
from collections import defaultdict, Counter
from agents.koutsu import KoutsuAI, can_win_koutsu_style
from display import print_full_state, format_pos_name, color_tile

focus_pos = WindPosition.EAST

def check_pon_or_kan(board, last_tile, last_pos, agents):
    """
    检查当前局面是否有人能胡牌或碰杠。

    Args:
        board (Board): 游戏板对象。
        last_tile (Tile): 上一张打出的牌。
        last_pos (Position): 上一张牌的打出者位置。
        agents (List[Agent]): 所有玩家的代理列表。

    Returns:
        Tuple[Union[str, bool], Position, Tile]: 返回一个元组，包含三个元素。
            - 第一个元素为 "win" 表示有人胡牌，或 "meld" 表示有人碰杠，或 False 表示无人胡牌且无人碰杠。
            - 第二个元素为胡牌或碰杠玩家的位置。
            - 第三个元素为胡牌或碰杠所用的牌。

    """
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


def determine_exchange_direction():
    """根据两颗骰子的点数和决定换牌方向。
    返回值：
        -1 表示换给上家（逆时针）
         0 表示换给对家
         1 表示换给下家（顺时针）
    """
    die1 = random.randint(1, 6)
    die2 = random.randint(1, 6)
    total = die1 + die2
    print(f"摇骰子决定换牌方向... 🎲 摇出的点数是 {die1} 和 {die2}，总和为 {total}")

    if total % 2 == 1:
        print("🎴 奇数，总和为奇数，换给对家")
        return 0
    elif total in (2, 6, 10):
        print("🎴 偶数，总和为 2, 6 或 10，顺时针换牌")
        return 1
    elif total in (4, 8, 12):
        print("🎴 偶数，总和为 4, 8 或 12，逆时针换牌")
        return -1
    else:
        print("⚠️ 异常点数，默认换给对家")
        return 0

# --- 只负责“分发”逻辑的函数，不做任何选牌／移除 ---
def exchange_three_tiles(board, tiles_by_player: dict[WindPosition, list[Tile]], direction: int):
    """
    tiles_by_player[pos] 是 pos 自己想换出的三张牌（已从手上移除）
    direction: -1=上家, 0=对家, 1=下家
    """
    for pos, tiles in tiles_by_player.items():
        colored = " ".join(color_tile(t) for t in tiles)
        print(f"  {format_pos_name(pos)} 选: [{colored}]")
    # 计算每家应收到谁的牌
    mapping = {}
    for src, tiles in tiles_by_player.items():
        if direction == 0:
            tgt = WindPosition((src.value + 2) % 4)
        elif direction == 1:
            tgt = src.next()
        elif direction == -1:
            tgt = WindPosition((src.value - 1) % 4)
        else:
            raise ValueError(f"未知换牌方向 {direction}")
        mapping.setdefault(tgt, []).extend(tiles)

    # 把牌发回手里
    for pos, incoming in mapping.items():
        board.get_hand(pos).extend(incoming)
        print(f"{format_pos_name(pos)} 收到: [{' '.join(map(color_tile, incoming))}]")

    print("✅ 换三张结束。")


# --- 1. 定缺环节：每家选一个花色作为缺门 ---
def dingque_phase(board, agents):
    """
    让每个玩家/AI 选择一个缺门（'man'、'pin'、'sou'）:
      - HumanAgent 通过输入选缺
      - SimpleAI / KoutsuAI 默认选自己手牌里数量最少的那一门
    返回一个 dict: { WindPosition: 'man'/'pin'/'sou' }
    """
    missing = {}
    for pos, agent in agents.items():
        hand = board.get_hand(pos)
        counts = Counter(t.suit.value for t in hand)
        if hasattr(agent, 'select_missing_suit'):   # HumanAgent
            choice = agent.select_missing_suit()      # 需实现此方法
        else:
            # 简单 AI：选最少的那门
            choice = min(('man','pin','sou'), key=lambda s: counts.get(s, 0))
        missing[pos] = choice
        print(f"{format_pos_name(pos)} 定缺 → {choice}")
    print("=== 定缺完成 ===\n")
    return missing

# --- 2. 严格执行“先打缺门”、不碰不杠缺门的规则 ---
def must_discard_dingque(agent) -> bool:
    """判定该 agent 是否手上还有缺门牌，若有则必须打出缺门。"""
    miss = agent.missing_suit
    hand = agent.board.get_hand(agent.position)
    return any(t.suit.value == miss for t in hand)

def can_win_dingque(agent, tile: Tile) -> bool:
    hand = agent.board.get_hand(agent.position) + [tile]
    # 如果最后手牌里还有缺门，则不能胡
    if any(t.suit.value == agent.missing_suit for t in hand):
        return False
    # 否则调用原有判胡
    return agent.can_win_on_tile(tile)



def main():
    focus_pos = WindPosition.EAST  # 👈 只观察东家
    board = MahjongBoard(rule="chuan")
    board.shuffle_and_deal()
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
    for pos in WindPosition:
        missing = agents[pos].select_missing_suit()
        agents[pos].missing_suit = missing
        print(f"{format_pos_name(agents[pos].position)} 定缺为 {missing}")

    # 庄家丢第一张牌
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

        if agents[current_pos].can_win_on_tile(drawn):
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

            discard = agents[current_pos].choose_discard()
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
                print_full_state(board, agents)
                continue

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
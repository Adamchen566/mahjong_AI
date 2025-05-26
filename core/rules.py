# rules.py
from typing import Optional, List
from core.tiles import *
from core.player import WindPosition
from core.display import *
from collections import Counter
import random
import json
from enum import Enum
from collections import Counter

suit_map = {
    'bamboo': 'SOU',
    'circle': 'PIN',
    'character': 'MAN',
    'dot': 'PIN',
    'wan': 'MAN',
}
honors = {
    'east': 'EAST',
    'south': 'SOUTH',
    'west': 'WEST',
    'north': 'NORTH',
    'red_dragon': 'RED',
    'green_dragon': 'GREEN',
    'white_dragon': 'WHITE',
}

def reconstruct_seven_pairs_hand(hand, melds):
    if not melds:
        return hand[:]
    # 只允许副露最后一组长度为2，其余必须为空
    if all(len(m) == 0 for m in melds[:-1]) and len(melds[-1]) == 2:
        return hand[:] + melds[-1][:]
    return None

def is_seven_pairs(hand, melds):
    from collections import Counter
    hand_for_check = reconstruct_seven_pairs_hand(hand, melds)
    if hand_for_check is None or len(hand_for_check) != 14:
        return False
    c = Counter(hand_for_check)
    pairs = [t for t, n in c.items() if n == 2]
    return len(pairs) == 7 and sum(c.values()) == 14

def is_dragon_seven_pairs(hand, melds):
    from collections import Counter
    hand_for_check = reconstruct_seven_pairs_hand(hand, melds)
    if hand_for_check is None or len(hand_for_check) != 14:
        return False
    c = Counter(hand_for_check)
    pair_count = sum(1 for v in c.values() if v == 2)
    quad_count = sum(1 for v in c.values() if v == 4)
    return pair_count == 6 and quad_count == 1 and sum(c.values()) == 14

def can_win_standard(
    hand: List[Tile],
    melds: List[List[Tile]],
    winning_tile: Optional[Tile] = None
) -> bool:    
    """
    标准胡牌：手牌 + winning_tile（若有）+ melds 区里的 melds 共计 4 组面子 + 1 对子。
    melds 中每个长度>=3 的副露都算一个面子。
    """
    # 1) 合并手牌与摸/荣的牌
    tiles = hand.copy()
    if winning_tile:
        # print(f"检查{winning_tile}是否点炮")
        tiles.append(winning_tile)
    # else:
        # print(f"检查是否自摸")

    # 2) 计算已有副露面子数
    meld_count = sum(1 for m in melds if len(m) >= 3)
    # 还需在手牌里凑出的面子数
    needed_sets = 4 - meld_count
    # print(f"副露面子数为 {meld_count}, 需要凑出 {needed_sets} 个面子")

    # 3) 总牌数必须等于 needed_sets*3 + 2 才有可能
    if len(tiles) != needed_sets * 3 + 2:
        print(f"hand牌数不符：{len(tiles)} != {needed_sets * 3 + 2}")
        return False

    # 4) 枚举对子
    for pair in set(tiles):
        if tiles.count(pair) < 2:
            continue
        remaining = tiles.copy()
        remaining.remove(pair)
        remaining.remove(pair)

        # 5) 递归检查能否拆出 needed_sets 个面子（刻子或顺子）
        if _can_form_n_melds(remaining, needed_sets):
            return True
    return False

def can_win_all(hand, melds, win_tile=None):
    return is_seven_pairs(hand, melds) or is_dragon_seven_pairs(hand, melds) or can_win_standard(hand, melds, win_tile)

def _can_form_n_melds(tiles: list[Tile], sets_left: int) -> bool:
    """辅助：tiles 必须能拆出 sets_left 个面子（顺子或刻子）且无剩余。"""
    if sets_left == 0:
        # 全拆完
        return len(tiles) == 0

    # 尝试刻子
    first = min(tiles)
    if tiles.count(first) >= 3:
        rem = tiles.copy()
        for _ in range(3):
            rem.remove(first)
        if _can_form_n_melds(rem, sets_left - 1):
            return True

    # 尝试顺子（仅对万/筒/条）
    suit, val = first.suit, first.value
    if isinstance(val, int) and suit.value in ("man", "pin", "sou"):
        seq = [Tile(suit, val + i) for i in (0, 1, 2)]
        if all(t in tiles for t in seq):
            rem = tiles.copy()
            for t in seq:
                rem.remove(t)
            if _can_form_n_melds(rem, sets_left - 1):
                return True

    return False

def check_pon_or_kan(board, last_tile, last_pos, agents, finished_players=None):
    if finished_players is None:
        finished_players = set()

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
        if responder_pos in finished_players:
            continue  # 已胡玩家跳过
        agent = agents[responder_pos]

        # ✅ 先检查是否能荣和
        hand = board.get_hand(responder_pos)
        melds = board.get_melds(responder_pos)
        print(f"检查 {format_pos_name(responder_pos)} 是否能胡牌 {color_tile(last_tile)}...")
        if can_win_standard(hand, melds, last_tile):
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
                print(f"{format_pos_name(responder_pos)} 杠后摸牌: {color_tile(drawn)}")
                board.sort_hand(responder_pos)

                # 胡牌检查
                if can_win_standard(board.get_hand(responder_pos), board.get_melds(responder_pos), drawn):
                    if agent.decide_win(drawn):
                        print(f"🎉🎉🎉 {format_pos_name(responder_pos)} 杠后自摸胡了！ 🎉🎉🎉")
                        board.add_meld(responder_pos, [drawn])
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
    # 用黄色高亮骰子结果
    DICE_COLOR = "\033[1;33m"
    print(f"摇骰子决定换牌方向... 🎲 摇出的点数是 {DICE_COLOR}{die1}{RESET} 和 {DICE_COLOR}{die2}{RESET}，总和为 {DICE_COLOR}{total}{RESET}")

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
        # 把缺门存到 agent，print_full_state 才能读到
        agent.missing_suit = choice
        # 用 COLOR_MAP 给缺门花色着色
        color = COLOR_MAP.get(choice, "")
        miss_colored = f"{color}{choice}{RESET}"
        print(f"{format_pos_name(pos)} 定缺 → {miss_colored}")
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

def vision_str_to_tile(tile_str):
    suit_map = {
        'bamboo': Suit.SOUZU,
        'circle': Suit.PINZU,
        'character': Suit.MANZU,
        'dot': Suit.PINZU,
        'wan': Suit.MANZU,
    }
    # honors 分别处理风和三元
    wind_map = {
        'east': Wind.EAST,
        'south': Wind.SOUTH,
        'west': Wind.WEST,
        'north': Wind.NORTH,
    }
    dragon_map = {
        'red_dragon': Dragon.RED,
        'green_dragon': Dragon.GREEN,
        'white_dragon': Dragon.WHITE,
    }
    if tile_str in wind_map:
        return Tile(Suit.WIND, wind_map[tile_str])
    if tile_str in dragon_map:
        return Tile(Suit.DRAGON, dragon_map[tile_str])
    if '_' in tile_str:
        suit, rank = tile_str.split('_')
        suit = suit.lower()
        if suit in suit_map:
            suit_enum = suit_map[suit]
            value = int(rank) if rank.isdigit() else rank
            return Tile(suit=suit_enum, value=value)
    raise ValueError(f"无法识别的 tile_str: {tile_str}")


def load_east_hand_from_vision(path="east_hand.json"):
    with open(path, "r", encoding="utf-8") as f:
        raw_tiles = json.load(f)
    return [vision_str_to_tile(s) for s in raw_tiles]

def tile_short_name(tile_name: str) -> str:
    if tile_name.endswith("man"):
        return tile_name[0] + "m"
    elif tile_name.endswith("pin"):
        return tile_name[0] + "p"
    elif tile_name.endswith("sou"):
        return tile_name[0] + "s"
    elif tile_name in ("ew", "sw", "ww", "nw"):
        return tile_name[0]  # e, s, w, n
    else:
        return tile_name  # 1d, 2d, 3d
    
def color_tile_short_name(tile_name: str) -> str:
    short = tile_short_name(tile_name)
    # 颜色部分同前
    if tile_name.endswith("man"):
        color = COLOR_MAP["man"]
    elif tile_name.endswith("pin"):
        color = COLOR_MAP["pin"]
    elif tile_name.endswith("sou"):
        color = COLOR_MAP["sou"]
    else:
        color = ""
    # 先不加颜色，居中好后再加色
    col_width = 3
    raw = f"{short:^{col_width}}"
    return f"{color}{raw}{RESET}"

def print_seen_matrix_chuan(board, agents, label="见牌矩阵"):
    tile_order = [
        '1man','2man','3man','4man','5man','6man','7man','8man','9man',
        '1pin','2pin','3pin','4pin','5pin','6pin','7pin','8pin','9pin',
        '1sou','2sou','3sou','4sou','5sou','6sou','7sou','8sou','9sou',
    ]
    seen_counts = {key: [1, 1, 1, 1] for key in tile_order}
    for pos in agents:
        for t in board.get_hand(pos):
            key = f"{t.value}{t.suit.value}"
            for idx in range(4):
                if seen_counts.get(key) and seen_counts[key][idx] == 1:
                    seen_counts[key][idx] = 0
                    break
        for meld in board.get_melds(pos):
            for t in meld:
                key = f"{t.value}{t.suit.value}"
                for idx in range(4):
                    if seen_counts.get(key) and seen_counts[key][idx] == 1:
                        seen_counts[key][idx] = 0
                        break
        for t in board.get_discards(pos):
            key = f"{t.value}{t.suit.value}"
            for idx in range(4):
                if seen_counts.get(key) and seen_counts[key][idx] == 1:
                    seen_counts[key][idx] = 0
                    break

    col_width = 3
    man_border = 9
    pin_border = 18

    print(f"\n== {label} ==")
    # 顶部边框
    print("┌" + ("─"*col_width + "┬")* (man_border-1) + "─"*col_width + "╥" +
          ("─"*col_width + "┬")* (pin_border-man_border-1) + "─"*col_width + "╥" +
          ("─"*col_width + "┬")* (len(tile_order)-pin_border-1) + "─"*col_width + "┐")
    # 牌名行
    print("│", end="")
    for i, key in enumerate(tile_order):
        raw = f"{tile_short_name(key):^{col_width}}"
        print(f"{color_tile_short_name(key)}│", end="")
        # 不加粗线！
    print()
    # 分割线
    print("├" + ("─"*col_width + "┼")* (man_border-1) + "─"*col_width + "╬" +
          ("─"*col_width + "┼")* (pin_border-man_border-1) + "─"*col_width + "╬" +
          ("─"*col_width + "┼")* (len(tile_order)-pin_border-1) + "─"*col_width + "┤")
    # 4行
    for row in range(4):
        print("│", end="")
        for i, key in enumerate(tile_order):
            v = seen_counts[key][row]
            # 统一宽度为3，字符左右各有空格，避免对齐错位
            print(f" {color_seen_num(v)} │", end="")
        print()
    # 底部边框
    print("└" + ("─"*col_width + "┴")* (man_border-1) + "─"*col_width + "╨" +
          ("─"*col_width + "┴")* (pin_border-man_border-1) + "─"*col_width + "╨" +
          ("─"*col_width + "┴")* (len(tile_order)-pin_border-1) + "─"*col_width + "┘\n")

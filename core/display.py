from core.player import WindPosition
from core.tiles import Tile

COLOR_MAP = {
    "sou": "\033[92m",     # bright green
    "man": "\033[91m",     # bright red
    "pin": "\033[93m",     # bright yellow
    "wind": "\033[90m",    # dark gray
    "dragon": "\033[95m",  # magenta
    "flower": "\033[96m",  # cyan
}

POSITION_COLOR = {
    WindPosition.EAST: "\033[34m",   # darker blue
    WindPosition.SOUTH: "\033[32m",  # darker green
    WindPosition.WEST: "\033[33m",   # darker yellow (brownish)
    WindPosition.NORTH: "\033[31m",  # darker red
}

RESET = "\033[0m"

def color_tile(t: Tile) -> str:
    color = COLOR_MAP.get(t.suit.value, "")
    return f"{color}{t}{RESET}"

def format_pos_name(pos: WindPosition) -> str:
    return f"{POSITION_COLOR[pos]}{pos.name}{RESET}"

def print_full_state(board, agents):
    """
    打印四家当前手牌、定缺和副露情况
    agents: Dict[WindPosition, Agent]，每个 agent 需有 missing_suit 属性
    """
    print("\n============================ 当前牌面 ============================")
    for pos in WindPosition:
        agent = agents.get(pos)
        # 定缺：用 color_tile 着色一个该门花色的示意牌（这里用1号）
        miss = getattr(agent, "missing_suit", None)
        if miss:
            color = COLOR_MAP.get(miss, "")
            # 显示“pin”“man”“sou”之一，带颜色
            miss_colored = f"{color}{miss}{RESET}"
            miss_str = f"(缺{miss_colored})"
        else:
            miss_str = ""
        # 手牌
        hand = sorted(board.get_hand(pos))
        hand_str = " ".join(color_tile(t) for t in hand)
        # 副露
        melds = board.get_melds(pos)
        if melds:
            meld_strs = []
            for meld in melds:
                meld_strs.append("".join(color_tile(t) for t in meld))
            meld_str = " 副露: " + " ".join(meld_strs)
        else:
            meld_str = ""
        # 输出
        print(f"{format_pos_name(pos)}{miss_str} 手牌: {hand_str}{meld_str}")
    print("------------------\n")
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

def print_full_state(board, pos_formatter=format_pos_name):
    for p in WindPosition:
        hand = board.get_hand(p)
        melds = board.get_melds(p)
        hand_str = ' '.join(color_tile(t) for t in hand)
        melds_str = ' | '.join(''.join(color_tile(t) for t in meld) for meld in melds) if melds else "无"
        print(f"{pos_formatter(p)} 手牌: {hand_str}")
        print(f"{pos_formatter(p)} 副露: {melds_str}")
from typing import Optional, Tuple, List
from collections import Counter

from core.player import WindPosition
from core.tiles import Tile
from core.display import color_tile, COLOR_MAP, RESET
from core.rules import can_win_standard

class HumanAgent:
    """
    手动玩家代理：所有操作在终端交互，包括定缺、换牌、打牌、碰杠和胡牌。
    """
    def __init__(self, position: WindPosition, board):
        self.position = position
        self.board = board
        self.missing_suit: Optional[str] = None

    def select_missing_suit(self) -> str:
        """让玩家手动选择定缺花色"""
        hand = self.board.get_hand(self.position)
        print("你的手牌: " + ' '.join(color_tile(t) for t in hand))
        while True:
            choice = input("请选择定缺门（man/pin/sou）: ").strip().lower()
            if choice in ("man", "pin", "sou"):
                self.missing_suit = choice
                return choice
            print("❌ 输入无效，请输入 man、pin 或 sou")

    def select_three_exchange(self) -> List[Tile]:
        """让玩家手动选择三张同花色牌进行换三张
        格式: 花色 编号1 编号2 编号3，例如 man 1 2 3"""
        hand = self.board.get_hand(self.position)
        print("你的手牌: " + ' '.join(color_tile(t) for t in hand))
        while True:
            inp = input("请输入要换出的三张同花色的牌（格式: man 1 2 3）: ").strip()
            parts = inp.split()
            if len(parts) != 4:
                print("❌ 格式错误，请输入 1 个花色 + 3 个数字，用空格分隔")
                continue
            suit = parts[0]
            if suit not in ("man", "pin", "sou"):
                print("❌ 花色输入错误，请输入 man、pin 或 sou")
                continue
            try:
                tiles: List[Tile] = []
                for r in parts[1:]:
                    rank = int(r)
                    tile = next(
                        t for t in hand
                        if t.suit.value == suit and t.value == rank
                    )
                    tiles.append(tile)
                return tiles
            except (ValueError, StopIteration):
                print("❌ 输入无效，请确保数字在 1-9 之间且牌在你的手牌中")

    def choose_discard(self, drawn_tile: Optional[Tile] = None) -> Tile:
        """让玩家手动选择要打出的牌，打印当前缺门并高亮新摸牌"""
        # 打印缺门
        if self.missing_suit:
            color = COLOR_MAP.get(self.missing_suit, "")
            miss_colored = f"{color}{self.missing_suit}{RESET}"
            print(f"当前缺门: {miss_colored}")
        # 打印手牌
        hand = self.board.get_hand(self.position)
        display = []
        for t in sorted(hand):
            ct = color_tile(t)
            if drawn_tile and t == drawn_tile:
                ct = f"\033[1;107m{ct}\033[0m"
            display.append(ct)
        print("你的手牌: " + ' '.join(display))

        while True:
            inp = input("请选择要打出的牌（例如 man5、pin7、sou2）: ").strip()
            for tile in hand:
                if str(tile) == inp:
                    return tile
            print("❌ 输入无效，请重新输入。")

    def decide_meld_action(self, last_tile: Tile) -> Optional[str]:
        """询问是否对上家打出的牌进行碰或杠"""
        hand = self.board.get_hand(self.position)
        count = hand.count(last_tile)
        if count >= 2:
            if input(f"是否碰 {last_tile}？(y/n): ").strip().lower() == 'y':
                return 'pon'
        if count >= 3:
            if input(f"是否杠 {last_tile}？(y/n): ").strip().lower() == 'y':
                return 'kan'
        return None

    def decide_concealed_or_added_kan(self) -> Tuple[Optional[str], Optional[Tile]]:
        """询问是否暗杠或加杠"""
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        counts = Counter(hand)
        for tile, cnt in counts.items():
            if cnt >= 4 and input(f"是否暗杠 {tile}？(y/n): ").strip().lower() == 'y':
                return 'ankan', tile
        for meld in melds:
            if len(meld) == 3 and hand.count(meld[0]) >= 1:
                if input(f"是否加杠 {meld[0]}？(y/n): ").strip().lower() == 'y':
                    return 'chakan', meld[0]
        return None, None

    def can_win(self) -> bool:
        """检查暗杠/加杠后补花或其他无需额外牌的场合，能否胡牌"""
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        return can_win_standard(hand, melds, None)

    def can_win_on_tile(self, tile: Tile) -> bool:
        """检查自摸或荣和时，手牌 + 新牌 + 副露 能否胡牌"""
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        return can_win_standard(hand, melds, tile)

    def decide_win(self, tile: Optional[Tile] = None) -> bool:
        """在可胡情形下询问玩家是否胡牌"""
        mode = '荣和' if tile is not None and tile not in self.board.get_hand(self.position) else '自摸'
        while True:
            choice = input(f"是否{mode}胡牌？(y/n): ").strip().lower()
            if choice in ('y','n'):
                return choice == 'y'
            print("❌ 输入无效，请输入 y 或 n。")
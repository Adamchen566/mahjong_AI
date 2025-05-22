from typing import Optional, Tuple, List
from core.player import WindPosition
from display import color_tile
from agents.simple import SimpleAI
from core.tiles import Tile

class HumanAgent(SimpleAI):
    def __init__(self, pos: WindPosition, board):
        # 调用父类构造，设置 position 和 board
        super().__init__(pos, board)

    def select_three_exchange(self) -> List[Tile]:
        """让玩家手动输入三张要换出的牌"""
        hand = self.board.get_hand(self.position)
        print("你的手牌: " + ' '.join(color_tile(t) for t in hand))
        while True:
            inp = input("请输入三张要换出的牌: ").strip()
            parts = inp.split()
            if len(parts) != 3:
                print("❌ 格式错误，请输入三张牌，用空格分隔")
                continue
            try:
                tiles: List[Tile] = []
                for code in parts:
                    tile = next(t for t in hand if str(t) == code)
                    tiles.append(tile)
                return tiles
            except StopIteration:
                print("❌ 输入的牌不在手牌中，请重新输入")

    def choose_discard(self, drawn_tile: Optional[Tile] = None) -> Tile:
        """让玩家手动选择要打出的牌"""
        hand = self.board.get_hand(self.position)
        sorted_hand = sorted(hand)
        # 高亮刚摸到的牌
        display = [f"\033[1;107m{color_tile(t)}\033[0m" if drawn_tile and t == drawn_tile else color_tile(t)
                   for t in sorted_hand]
        print("你的手牌: " + ' '.join(display))
        while True:
            inp = input("请选择要打出的牌: ").strip()
            for tile in hand:
                if str(tile) == inp:
                    return tile
            print("❌ 输入无效，请重新输入。")

    def decide_win(self, tile: Optional[Tile] = None) -> bool:
        choice = input(f"是否胡{'（荣和）' if tile else '（自摸）'}？(y/n): ").strip().lower()
        return choice == 'y'

    def decide_meld_action(self, last_tile: Tile) -> Optional[str]:
        """询问玩家是否碰/杠"""
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
        """询问玩家是否暗杠或加杠"""
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        # 暗杠检测
        counts = {tile: hand.count(tile) for tile in set(hand)}
        for tile, cnt in counts.items():
            if cnt >= 4 and input(f"是否暗杠 {tile}？(y/n): ").strip().lower() == 'y':
                return 'ankan', tile
        # 加杠检测
        for meld in melds:
            if len(meld) == 3 and hand.count(meld[0]) >= 1 and input(f"是否加杠 {meld[0]}？(y/n): ").strip().lower() == 'y':
                return 'chakan', meld[0]
        return None, None
from display import color_tile
from agents.simple import SimpleAI
from core.tiles import Tile

class HumanAgent(SimpleAI):
    def __init__(self, pos, board):
        self.pos = pos
        self.board = board

    def select_three_exchange(self) -> list[Tile]:
        """让玩家手动输入三张要换出的牌"""
        hand = self.board.get_hand(self.pos)
        # 显示当前手牌
        colored = ' '.join(color_tile(t) for t in hand)
        print("你的手牌: " + colored)
        while True:
            inp = input("请输入三张要换出的牌（格式如 man3 pin5 sou7，用空格分隔）: ").strip()
            parts = inp.split()
            if len(parts) != 3:
                print("❌ 格式错误，请输入三张牌，用空格分隔")
                continue
            try:
                tiles = []
                for code in parts:
                    # 找到对应 Tile 对象
                    tile = next(t for t in hand if str(t) == code)
                    tiles.append(tile)
                return tiles
            except StopIteration:
                print("❌ 输入的牌不在手牌中，请重新输入")

    def choose_discard(self, drawn_tile=None):
        hand = self.board.get_hand(self.pos)
        tiles = sorted(hand)
        colored = []
        for t in tiles:
            ct = color_tile(t)
            if drawn_tile and t == drawn_tile:
                ct = f"\033[1;107m{ct}\033[0m"
            colored.append(ct)
        print("你的手牌: " + ' '.join(colored))

        while True:
            discard_input = input("请选择要打出的牌（例如 man5、sou2、pin7）: ").strip()
            for tile in hand:
                if str(tile) == discard_input:
                    return tile
            print("❌ 输入无效，请重新输入。")

    def decide_win(self, tile=None):
        choice = input(f"是否胡{'（荣和）' if tile else '（自摸）'}？(y/n): ").strip().lower()
        return choice == 'y'

    def decide_meld_action(self, last_tile):
        hand = self.board.get_hand(self.pos)
        count = sum(1 for t in hand if t == last_tile)
        if count >= 2:
            choice = input(f"是否碰 {last_tile}？(y/n): ").strip().lower()
            if choice == 'y':
                return 'pon'
        if count >= 3:
            choice = input(f"是否杠 {last_tile}？(y/n): ").strip().lower()
            if choice == 'y':
                return 'kan'
        return 'pass'

    def decide_concealed_or_added_kan(self):
        hand = self.board.get_hand(self.pos)
        melds = self.board.get_melds(self.pos)

        # 检查暗杠
        counter = {}
        for tile in hand:
            counter[str(tile)] = counter.get(str(tile), 0) + 1
        for tile_str, count in counter.items():
            if count >= 4:
                choice = input(f"是否暗杠 {tile_str}？(y/n): ").strip().lower()
                if choice == 'y':
                    tile = next(t for t in hand if str(t) == tile_str)
                    return "ankan", tile

        # 检查加杠
        for meld in melds:
            if len(meld) == 3 and all(tile == meld[0] for tile in meld):
                tile = meld[0]
                if hand.count(tile) >= 1:
                    choice = input(f"是否加杠 {tile}？(y/n): ").strip().lower()
                    if choice == 'y':
                        return "chakan", tile

        return None, None

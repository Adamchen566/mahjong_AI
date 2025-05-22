from display import color_tile
class HumanAgent:
    def __init__(self, pos, board):
        self.pos = pos
        self.board = board

    def choose_discard(self, drawn_tile=None):
        hand = self.board.get_hand(self.pos)
        tiles = sorted(hand)
        colored = []
        for t in tiles:
            ct = color_tile(t)
            if drawn_tile and t == drawn_tile:
                ct = f"\033[1;107m{ct}\033[0m"  # 高亮背景白
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

        # 🔍 检查暗杠机会
        counter = {}
        for tile in hand:
            counter[str(tile)] = counter.get(str(tile), 0) + 1
        for tile_str, count in counter.items():
            if count >= 4:
                choice = input(f"是否暗杠 {tile_str}？(y/n): ").strip().lower()
                if choice == 'y':
                    tile = next(t for t in hand if str(t) == tile_str)
                    return "ankan", tile

        # 🔍 检查加杠机会
        for meld in melds:
            if len(meld) == 3 and all(tile == meld[0] for tile in meld):
                tile = meld[0]
                if hand.count(tile) >= 1:
                    choice = input(f"是否加杠 {tile}？(y/n): ").strip().lower()
                    if choice == 'y':
                        return "chakan", tile

        # 没有可选项时不询问
        return None, None

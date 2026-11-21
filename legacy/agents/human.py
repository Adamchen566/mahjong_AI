from typing import Optional, Tuple, List
from core.tiles import Tile
from core.rules import can_win_standard
from core.tilesCounter import MahjongCounter
from core.display import color_tile, COLOR_MAP, RESET

class HumanAgent:
    """
    适配终端调试的玩家代理，所有交互用 input()。
    """
    def __init__(self, position, board, all_players):
        self.position = position
        self.board = board
        self.counter = MahjongCounter()
        self.all_players = all_players  # 四家玩家对象
        self.wall_counter = MahjongCounter()

    def sync_counter(self):
        # 获取全部信息，写入 counter
        self.counter = MahjongCounter()  # 先清空
        # 手牌
        for tile in self.board.get_hand(self.position):
            self.counter.add(tile, channel=0)
        # 副露
        for meld in self.board.get_melds(self.position):
            for tile in meld:
                self.counter.add(tile, channel=1)
        # 弃牌
        for tile in self.board.get_discards(self.position):
            self.counter.add(tile, channel=2)

    def sync_all(self):
        # 本家
        self.counter.reset()
        self.counter.fill_from_list(self.board.get_hand(self.position), channel=0)
        # 副露
        for meld in self.board.get_melds(self.position):
            for tile in meld:
                self.counter.add(tile, channel=1)
        # 弃牌
        for tile in self.board.get_discards(self.position):
            self.counter.add(tile, channel=2)
        # 牌墙（神谕）
        self.wall_counter.reset()
        for tile in self.board.get_wall():
            self.wall_counter.add(tile, channel=0)
        # 其它玩家
        for p in self.all_players:
            if p.position == self.position:
                continue
            p.counter.reset()
            p.counter.fill_from_list(self.board.get_hand(p.position), channel=0)
            for meld in self.board.get_melds(p.position):
                for tile in meld:
                    p.counter.add(tile, channel=1)
            for tile in self.board.get_discards(p.position):
                p.counter.add(tile, channel=2)

    def print_all_counters(self):
        print(f"\n=== 玩家 {self.position} 信息 ===")
        self.counter.print_counter(f"玩家 {self.position} 计数器")
        for p in self.all_players:
            if p.position != self.position:
                p.counter.print_counter(f"对家 {p.position} 计数器")
        self.wall_counter.print_counter("牌墙计数器")

    # 在每次操作（如出牌、摸牌、操作副露等）前后，调用这两个方法
    def before_action(self):
        self.sync_all()
        self.print_all_counters()

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

        # 让玩家选择要出的牌
        while True:
            inp = input("请输入要打出的牌（如 5man 或 7pin 或 3sou），或者输入下标（如 0 1 2...）: ").strip()
            hand_sorted = sorted(hand)
            # 尝试按下标
            if inp.isdigit():
                idx = int(inp)
                if 0 <= idx < len(hand_sorted):
                    return hand_sorted[idx]
                else:
                    print("❌ 下标超出范围")
            else:
                # 尝试按牌名匹配
                try:
                    # 支持格式如 5man 3sou 4pin
                    import re
                    m = re.fullmatch(r'(\d)(man|pin|sou)', inp)
                    if m:
                        rank = int(m.group(1))
                        suit = m.group(2)
                        for t in hand_sorted:
                            if t.value == rank and t.suit.value == suit:
                                return t
                        print("❌ 该牌不在你的手牌中")
                    else:
                        print("❌ 输入格式错误，请重新输入")
                except Exception:
                    print("❌ 输入无法识别，请重新输入")

    def decide_meld_action(self, last_tile):
        hand = self.board.get_hand(self.position)
        cnt = hand.count(last_tile)
        if cnt >= 3:
            ans = input(f"你有三张{last_tile}，是否要杠？(y/n): ")
            if ans.lower().startswith("y"):
                return 'kan'
        if cnt >= 2:
            ans = input(f"你有两张{last_tile}，是否要碰？(y/n): ")
            if ans.lower().startswith("y"):
                return 'pon'
        return None

    def can_win(self):
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        # 假设已有can_win_standard
        return can_win_standard(hand, melds, None)

    def decide_win(self, tile=None):
        mode = '荣和' if tile is not None and tile not in self.board.get_hand(self.position) else '自摸'
        ans = input(f"是否{mode}胡牌？(y/n): ")
        return ans.lower().startswith("y")

    # 你可以在回合或每次操作后调用
    def update_and_sync(self):
        self.sync_counter()
        # print("当前计数器内容：\n", self.counter.get_counter())
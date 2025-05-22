from core.player import WindPosition
from core.tiles import Tile
from typing import Optional, Tuple
from collections import Counter, defaultdict

class SimpleAI:
    def __init__(self, position: WindPosition, board):
        self.position = position
        self.board = board

    def select_three_exchange(self) -> list[Tile]:
        """选择三张同花色的牌用于换三张，优先选择 >=3 且数量最少的花色"""
        hand = self.board.get_hand(self.position)
        suits = defaultdict(list)
        for tile in hand:
            suit = tile.suit.value
            if suit in ("man", "pin", "sou"):
                suits[suit].append(tile)
        # 筛选出至少3张的花色
        valid = {s: tiles for s, tiles in suits.items() if len(tiles) >= 3}
        if not valid:
            # 若无任何花色满足条件，返回空列表
            return []
        # 选择最少牌数的花色
        chosen_suit = min(valid.keys(), key=lambda s: len(valid[s]))
        return valid[chosen_suit][:3]


    def choose_discard(self) -> Tile:
        # 简单策略：打出手中最少的那张牌
        hand = self.board.get_hand(self.position)
        counter = Counter(hand)
        return min(counter, key=lambda t: (counter[t], str(t)))

    def decide_meld_action(self, tile: Tile) -> Optional[str]:
        hand = self.board.get_hand(self.position)
        count = hand.count(tile)
        if count >= 3:
            return 'kan'
        elif count >= 2:
            return 'pon'
        return None

    def decide_concealed_or_added_kan(self) -> Tuple[Optional[str], Optional[Tile]]:
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        counter = Counter(hand)

        for tile, count in counter.items():
            if count == 4:
                return 'ankan', tile

        for meld in melds:
            # 只支持碰（三张），就假设副露中一定是三张相同的
            if len(meld) == 3 and meld[0] in hand:
                return 'chakan', meld[0]
            
        return None, None

    def can_win(self) -> bool:
        hand = self.board.get_hand(self.position)
        return self.is_winning_hand(hand)

    def can_win_on_tile(self, tile: Tile) -> bool:
        hand = self.board.get_hand(self.position) + [tile]
        return self.is_winning_hand(hand)

    def decide_win(self, tile: Optional[Tile] = None) -> bool:
        # 简单策略：总是胡
        return True

    def is_winning_hand(self, tiles: list[Tile]) -> bool:
        # 简化版胡牌判定，仅检查 4 面子 + 1 对子的基本形式
        if len(tiles) % 3 != 2:
            print("手牌数量不符合胡牌条件")
            return False

        from itertools import combinations
        tiles.sort()
        counter = Counter(tiles)
        print(f"Counter: {counter}")

        pairs = [t for t in counter if counter[t] >= 2]
        for pair in pairs:
            remaining = tiles.copy()
            remaining.remove(pair)
            remaining.remove(pair)
            if self.can_form_melds(remaining):
                return True
        return False

    def can_form_melds(self, tiles: list[Tile]) -> bool:
        if not tiles:
            return True
        tiles.sort()
        first = tiles[0]
        count = tiles.count(first)

        # 刻子（三张一样）
        if count >= 3:
            for _ in range(3):
                tiles.remove(first)
            return self.can_form_melds(tiles)

        # 顺子（仅适用于万/筒/条）
        if first.suit.value in {"man", "pin", "sou"} and isinstance(first.value, int):
            try:
                second = Tile(first.suit, first.value + 1)
                third = Tile(first.suit, first.value + 2)
                if second in tiles and third in tiles:
                    tiles.remove(first)
                    tiles.remove(second)
                    tiles.remove(third)
                    return self.can_form_melds(tiles)
            except Exception:
                pass

        return False
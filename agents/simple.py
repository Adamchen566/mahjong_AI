from typing import Optional, Tuple, List
from collections import Counter, defaultdict

from core.player import WindPosition
from core.tiles import Tile
from core.rules import can_win_standard


class SimpleAI:
    def __init__(self, position: WindPosition, board):
        self.position = position
        self.board = board

    def select_three_exchange(self) -> List[Tile]:
        """选择三张同花色的牌用于换三张，优先选择 >=3 且数量最少的花色"""
        hand = self.board.get_hand(self.position)
        suits = defaultdict(list)
        for tile in hand:
            suit = tile.suit.value
            if suit in ("man", "pin", "sou"):
                suits[suit].append(tile)
        valid = {s: tiles for s, tiles in suits.items() if len(tiles) >= 3}
        if not valid:
            return []
        chosen_suit = min(valid.keys(), key=lambda s: len(valid[s]))
        return valid[chosen_suit][:3]

    def select_missing_suit(self) -> str:
        """默认选择当前手牌中数量最少的花色作为定缺"""
        hand = self.board.get_hand(self.position)
        counts = Counter(tile.suit.value for tile in hand)
        return min(("man", "pin", "sou"), key=lambda s: counts.get(s, 0))

    def choose_discard(self) -> Tile:
        """简单策略：打出手中出现次数最少的那张牌"""
        hand = self.board.get_hand(self.position)
        counter = Counter(hand)
        return min(counter, key=lambda t: (counter[t], str(t)))

    def decide_meld_action(self, tile: Tile) -> Optional[str]:
        """决定是否碰或杠"""
        hand = self.board.get_hand(self.position)
        count = hand.count(tile)
        if count >= 3:
            return 'kan'
        elif count >= 2:
            return 'pon'
        return None

    def decide_concealed_or_added_kan(self) -> Tuple[Optional[str], Optional[Tile]]:
        """决定是否暗杠或加杠"""
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        counter = Counter(hand)

        # 暗杠
        for tile, cnt in counter.items():
            if cnt == 4:
                return 'ankan', tile
        # 加杠
        for meld in melds:
            if len(meld) == 3 and all(t == meld[0] for t in meld):
                return 'chakan', meld[0]

        return None, None

    def can_win(self) -> bool:
        """
        杠后补花或其他不带额外牌的场合判胡，
        手牌 + 副露 区 + None
        """
        return can_win_standard(
            self.board.get_hand(self.position),
            self.board.get_melds(self.position),
            None
        )

    def can_win_on_tile(self, tile: Tile) -> bool:
        """
        自摸或荣和判胡，
        手牌 + 副露 区 + 这张牌
        """
        return can_win_standard(
            self.board.get_hand(self.position),
            self.board.get_melds(self.position),
            tile
        )

    def decide_win(self, tile: Optional[Tile] = None) -> bool:
        """简单策略：如果能胡，总是胡"""
        return True
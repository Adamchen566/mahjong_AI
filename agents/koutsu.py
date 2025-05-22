from core.player import WindPosition
from core.tiles import Tile
from collections import Counter
from typing import Optional, Tuple
from agents.simple import SimpleAI

class KoutsuAI(SimpleAI):
    """基于 SimpleAI 的增强版 AI，支持可配置的荣和/自摸权限"""
    def __init__(self, position: WindPosition, board, allow_ron: bool = True, allow_tsumo: bool = True):
        super().__init__(position, board)
        self.allow_ron = allow_ron
        self.allow_tsumo = allow_tsumo

    def decide_win(self, tile: Optional[Tile] = None) -> bool:
        """优先使用标准判胡：四组面子+一对（顺子或刻子均可）"""
        # 权限检查
        if tile and not self.allow_ron:
            return False
        if tile is None and not self.allow_tsumo:
            return False
        # 自摸或荣和调用统一判胡接口
        if tile:
            return self.can_win_on_tile(tile)
        else:
            return self.can_win()

    def can_win(self) -> bool:
        """杠后或其他无 incoming_tile 场合判胡"""
        return super().can_win()

    # can_win_on_tile 默认继承自 SimpleAI

    def choose_discard(self) -> Tile:
        """出牌策略：听牌时可打印提示，然后根据剩余张数加权选择"""
        if self.can_win():
            print(f"[{self.position.name}] 处于听牌状态但选择不胡。")

        hand = self.board.get_hand(self.position)
        visible = self.board.get_visible_tiles()
        visible_counter = Counter(visible)
        hand_counter = Counter(hand)

        score = {}
        for t in hand:
            remaining = 4 - visible_counter[t] - hand_counter[t]
            is_pair = hand_counter[t] >= 2
            is_triplet = hand_counter[t] >= 3
            penalty = 10 if is_triplet else (5 if is_pair else 0)
            score[t] = remaining + penalty

        return min(hand, key=lambda t: (score[t], str(t)))

    def decide_meld_action(self, tile: Tile) -> Optional[str]:
        """决定是否碰 or 杠"""
        hand = self.board.get_hand(self.position)
        count = hand.count(tile)
        if count >= 3:
            return 'kan'
        elif count >= 2:
            return 'pon'
        return None

    def decide_concealed_or_added_kan(self) -> Tuple[Optional[str], Optional[Tile]]:
        """决定暗杠 or 加杠"""
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        counter = Counter(hand)

        # 暗杠
        for t, cnt in counter.items():
            if cnt == 4:
                return "ankan", t
        # 加杠
        for meld in melds:
            if len(meld) == 3 and all(x == meld[0] for x in meld) and meld[0] in hand:
                return "chakan", meld[0]
        return None, None
from core.player import WindPosition
from core.tiles import Tile
from collections import Counter
from agents.simple import SimpleAI
from typing import Optional, Tuple


class KoutsuAI(SimpleAI):
    def __init__(self, position, board, allow_ron=True, allow_tsumo=True):
        super().__init__(position, board)
        self.allow_ron = allow_ron
        self.allow_tsumo = allow_tsumo
    
    def decide_win(self, tile: Optional[Tile] = None) -> bool:
        if tile and not self.allow_ron:
            return False
        if tile is None and not self.allow_tsumo:
            return False
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        return can_win_koutsu_style(hand, melds, tile)
    
    def choose_discard(self) -> Tile:
        if self.can_win():
            print(f"[{self.position.name}] 处于听牌状态但选择不胡。")


        hand = self.board.get_hand(self.position)
        visible = self.board.get_visible_tiles()
        visible_counter = Counter(visible)
        hand_counter = Counter(hand)

        score = {}
        for tile in hand:
            # 剩余张数 = 4 - 场上已见张数 - 手牌中该牌数量
            remaining = 4 - visible_counter[tile] - hand_counter[tile]
            # 优先保留对子/刻子
            is_pair = hand_counter[tile] >= 2
            is_triplet = hand_counter[tile] >= 3
            penalty = 10 if is_triplet else (5 if is_pair else 0)
            score[tile] = remaining + penalty

        return min(hand, key=lambda t: (score[t], str(t)))


    def decide_meld_action(self, tile: Tile) -> Optional[str]:
        hand = self.board.get_hand(self.position)
        count = hand.count(tile)
        if count >= 3:
            return 'kan'
        elif count >= 2:
            return 'pon'
        return None
    
    def can_win(self) -> bool:
        hand = self.board.get_hand(self.position)
        return self.is_winning_hand(hand)
    
    def decide_concealed_or_added_kan(self) -> Tuple[Optional[str], Optional[Tile]]:
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        counter = Counter(hand)

        # 暗杠判断：手中有4张相同的
        for tile, count in counter.items():
            if count == 4:
                return "ankan", tile

        # 加杠判断：手中有1张，副露中有该牌的刻子
        for meld in melds:
            if len(meld) == 3 and all(t == meld[0] for t in meld) and meld[0] in hand:
                return "chakan", meld[0]
        return None, None
    
def can_win_koutsu_style(hand: list[Tile], melds: list[list[Tile]], incoming_tile: Optional[Tile] = None) -> bool:
    tiles = hand.copy()
    if incoming_tile:
        tiles.append(incoming_tile)
    for meld in melds:
        tiles.extend(meld)

    if len(tiles) != 14:
        return False

    tiles.sort()
    counter = Counter(tiles)

    for t in counter:
        if counter[t] >= 2:
            temp = tiles.copy()
            temp.remove(t)
            temp.remove(t)
            triplets = 0
            i = 0
            while i <= len(temp) - 3:
                if temp[i] == temp[i + 1] == temp[i + 2]:
                    del temp[i:i + 3]
                    triplets += 1
                else:
                    i += 1
            if triplets == 4 and not temp:
                return True

    return False
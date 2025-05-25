from typing import Optional, Tuple, List, Dict
from collections import Counter, defaultdict
from typing import Optional, Dict, Any
from core.player import WindPosition
from core.tiles import Tile
from core.rules import can_win_standard
import json
from datetime import datetime


class OracleAI:
    """
    神谕AI：可见所有玩家手牌、明牌、弃牌、牌墙。可用于纯速胡/大牌或未来扩展复杂博弈策略。
    """
    LOG_FILE = "oracle_ai_log.txt"
    def __init__(self, position: WindPosition, board):
        self.position = position
        self.board = board
        self.full_info = {}

    def update_full_info(self):
        """每次决策前刷新全场明牌信息，方便后续更复杂策略分析"""
        # 注意：get_all_hands返回引用，如果你需要不可变copy，可以用 .copy()
        self.full_info['hands'] = {pos: list(self.board.get_hand(pos)) for pos in WindPosition}
        self.full_info['melds'] = {pos: [meld.copy() for meld in self.board.get_melds(pos)] for pos in WindPosition}
        self.full_info['discards'] = {pos: list(self.board.get_discards(pos)) for pos in WindPosition}
        self.full_info['wall'] = list(self.board.wall)
        # 可在此加入更多统计信息，如所有已见牌、剩余某张牌数量等

    def select_three_exchange(self) -> List[Tile]:
        """换三张策略：保留自己进攻性最强的花色，将最少且分散的花色作为换牌对象"""
        self.update_full_info()
        hand = self.board.get_hand(self.position)
        suits = defaultdict(list)
        for tile in hand:
            suit = tile.suit.value
            if suit in ("man", "pin", "sou"):
                suits[suit].append(tile)
        # 找到数量>=3且张数最少的花色（以速胡为主，后续可引入明牌分析）
        valid = {s: tiles for s, tiles in suits.items() if len(tiles) >= 3}
        if not valid:
            return []
        chosen_suit = min(valid.keys(), key=lambda s: len(valid[s]))
        self.log("select_three_exchange", {"exchange": [str(t) for t in chosen_suit]})
        # 未来可进一步优先换孤张/断张
        return valid[chosen_suit][:3]

    def select_missing_suit(self) -> str:
        """定缺：选择手牌中数量最少的花色"""
        self.update_full_info()
        hand = self.board.get_hand(self.position)
        counts = Counter(tile.suit.value for tile in hand)
        return min(("man", "pin", "sou"), key=lambda s: counts.get(s, 0))

    def choose_discard(self) -> Tile:
        """出牌：速胡为主，简单策略为打出现次数最少的牌
        未来可扩展：用明牌信息避免打危险牌或打出“无效”牌
        """
        self.update_full_info()
        hand = self.board.get_hand(self.position)
        counter = Counter(hand)
        # 最少数优先，字典序辅助稳定性
        tile = min(counter, key=lambda t: (counter[t], str(t)))
        self.log("choose_discard", {"discard": str(tile)})
        return min(counter, key=lambda t: (counter[t], str(t)))

    def decide_meld_action(self, tile: Tile) -> Optional[str]:
        """吃碰杠决策：速胡为主，能碰能杠就碰杠"""
        self.update_full_info()
        hand = self.board.get_hand(self.position)
        count = hand.count(tile)
        if count >= 3:
            self.log("decide_meld_action: kan")
            return 'kan'
        elif count >= 2:
            self.log("decide_meld_action: pon")
            return 'pon'
        return None

    def decide_concealed_or_added_kan(self) -> Tuple[Optional[str], Optional[Tile]]:
        """暗杠/加杠决策：有就做，纯进攻思路"""
        self.update_full_info()
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        counter = Counter(hand)
        # 暗杠
        for tile, cnt in counter.items():
            if cnt == 4:
                self.log("decide_meld_action: ankan")
                return 'ankan', tile
        # 加杠
        for meld in melds:
            if len(meld) == 3 and all(t == meld[0] for t in meld):
                self.log("decide_meld_action: chakan")
                return 'chakan', meld[0]
        return None, None

    def can_win(self) -> bool:
        """判断自家手牌+副露能否和牌"""
        # 明牌AI可用full_info做更深层分析，当前保持接口一致
        return can_win_standard(
            self.board.get_hand(self.position),
            self.board.get_melds(self.position),
            None
        )

    def can_win_on_tile(self, tile: Tile) -> bool:
        """判断摸/点能否胡"""
        return can_win_standard(
            self.board.get_hand(self.position),
            self.board.get_melds(self.position),
            tile
        )

    def decide_win(self, tile: Optional[Tile] = None) -> bool:
        """能胡就胡，永远选择进攻"""
        return True

    # 可以根据需要加辅助函数，例如统计某牌剩余数、分析对家听口等

    def log(self, action: str, info: dict = None):
        log_dict = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "position": self.position.name,
            "action": action,
            "hand": [str(t) for t in self.board.get_hand(self.position)],
            "full_info": {
                k: {p.name: [str(t) for t in v[p]] for p in v} if isinstance(v, dict) else str(v)
                for k, v in self.full_info.items()
            }
        }
        if info:
            log_dict["decision"] = info
        # 以json行格式写入，方便后续处理，也可写为纯文本
        with open(self.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_dict, ensure_ascii=False) + "\n")



    


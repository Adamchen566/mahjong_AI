# main.py
from core.board import MahjongBoard
from core.player import WindPosition

board = MahjongBoard(rule="nanjing")  # 默认东家
board.shuffle_and_deal()
board.sort_all_hands()

for pos in WindPosition:
    hand = board.get_hand(pos)
    print(f"{pos.name} 家 手牌({len(hand)}张: {[str(t) for t in hand]}")

print(f"摸牌前 {WindPosition.EAST.name} 家 手牌: {[str(t) for t in board.get_hand(WindPosition.EAST)]}")

# 模拟东家摸牌
tile = board.draw_tile(WindPosition.EAST)
print(f"东家摸牌: {tile}")

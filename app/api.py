from flask import Flask, jsonify
from core.board import MahjongBoard
from core.player import WindPosition

app = Flask(__name__)

# 初始化麻将牌局
board = MahjongBoard(rule="nanjing")
board.shuffle_and_deal()
board.sort_all_hands()

def tile_to_dict(t):
    return {
        "suit": str(t.suit.value) if hasattr(t.suit, 'value') else str(t.suit),
        "value": str(t.value.value) if hasattr(t.value, 'value') else str(t.value)
    }

@app.route("/api/debug_hands")
def debug_hands():
    try:
        hands = {
            pos.name: [tile_to_dict(t) for t in board.get_hand(pos)]
            for pos in WindPosition
        }
        wall = [tile_to_dict(t) for t in board.wall]

        return jsonify({"hands": hands, "wall": wall})
    except Exception as e:
        print("❌ Flask 出错:", e)
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(debug=True)

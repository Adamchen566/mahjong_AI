import tkinter as tk
from tkinter import Canvas, PhotoImage
from core.board import MahjongBoard
from core.player import WindPosition
from agents.koutsu import KoutsuAI, can_win_koutsu_style
from display import format_pos_name
import os

class MahjongStyledGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("川麻对局 - 精致界面")
        self.root.geometry("1000x700")
        self.board_canvas = Canvas(self.root, width=1000, height=700, bg="#054d30")
        self.board_canvas.pack()

        self.tile_images = self.load_tile_images()

        self.start_button = tk.Button(self.root, text="开始对局", command=self.run_game, font=("Helvetica", 14), bg="gold")
        self.start_button.place(x=450, y=20)

        self.board = None
        self.agents = None

    def load_tile_images(self):
        # 临时方案：使用字体/颜色模拟
        return {}

    def draw_table_layout(self):
        self.board_canvas.delete("all")

        # 玩家牌区背景
        self.board_canvas.create_rectangle(380, 600, 620, 660, fill="#004d00", outline="white")  # 下家
        self.board_canvas.create_rectangle(380, 40, 620, 100, fill="#004d00", outline="white")   # 上家
        self.board_canvas.create_rectangle(40, 250, 100, 450, fill="#004d00", outline="white")   # 左家
        self.board_canvas.create_rectangle(900, 250, 960, 450, fill="#004d00", outline="white")  # 右家

        self.board_canvas.create_text(500, 320, text="麻将对局中", font=("Helvetica", 20), fill="white")

    def draw_hand(self, pos, tiles):
        spacing = 30
        if pos == WindPosition.SOUTH:
            for i, t in enumerate(tiles):
                self.board_canvas.create_text(400 + i * spacing, 620, text=str(t), fill="white", font=("Helvetica", 14))
        elif pos == WindPosition.NORTH:
            for i, t in enumerate(tiles):
                self.board_canvas.create_text(400 + i * spacing, 80, text=str(t), fill="white", font=("Helvetica", 14))
        elif pos == WindPosition.WEST:
            for i, t in enumerate(tiles):
                self.board_canvas.create_text(60, 260 + i * spacing, text=str(t), fill="white", font=("Helvetica", 14))
        elif pos == WindPosition.EAST:
            for i, t in enumerate(tiles):
                self.board_canvas.create_text(940, 260 + i * spacing, text=str(t), fill="white", font=("Helvetica", 14))

    def run_game(self):
        self.board = MahjongBoard(rule="chuan")
        self.board.shuffle_and_deal()
        self.board.sort_all_hands()
        self.agents = {pos: KoutsuAI(pos, self.board) for pos in WindPosition}

        finished = set()
        dealer = WindPosition.EAST
        current_pos = dealer

        self.draw_table_layout()
        for pos in WindPosition:
            self.draw_hand(pos, self.board.get_hand(pos))

        discard = self.agents[dealer].choose_discard()
        self.board.discard_tile(dealer, discard)
        current_pos = dealer.next()

        while not self.board.is_draw():
            if current_pos in finished:
                current_pos = current_pos.next()
                continue

            try:
                drawn = self.board.draw_tile(current_pos)
                self.board.sort_hand(current_pos)
            except:
                break

            hand = self.board.get_hand(current_pos)
            melds = self.board.get_melds(current_pos)

            if can_win_koutsu_style(hand, melds):
                if self.agents[current_pos].decide_win():
                    finished.add(current_pos)
                    if len(finished) >= 3:
                        break
                    current_pos = current_pos.next()
                    continue

            discard = self.agents[current_pos].choose_discard()
            self.board.discard_tile(current_pos, discard)
            current_pos = current_pos.next()

        self.board_canvas.create_text(500, 360, text="对局结束", font=("Helvetica", 16), fill="yellow")
        for pos in finished:
            self.board_canvas.create_text(500, 400 + 20 * pos.value, text=f"{format_pos_name(pos)} 胡了！", fill="white")


if __name__ == "__main__":
    root = tk.Tk()
    app = MahjongStyledGUI(root)
    root.mainloop()
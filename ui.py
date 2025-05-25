import tkinter as tk
from tkinter import messagebox

class MahjongTableUI:
    def __init__(self, board, agents):
        self.board = board
        self.agents = agents
        self.root = tk.Tk()
        self.root.title("Mahjong Game UI")
        self.canvas = tk.Canvas(self.root, width=800, height=800, bg="#386E4A")
        self.canvas.pack()
        # 位置坐标参考
        self.player_pos = {
            "EAST": (400, 700),
            "SOUTH": (700, 400),
            "WEST": (400, 100),
            "NORTH": (100, 400),
        }
        self.tile_width = 35
        self.tile_height = 55

        self.current_action = None
        self.selected_tiles = []

    def draw_table(self):
        self.canvas.delete("all")
        # 画四家手牌/副露
        for pos in self.board.hands:
            hand = self.board.get_hand(pos)
            hx, hy = self.player_pos[pos.name]
            for i, tile in enumerate(sorted(hand)):
                x = hx + (i - len(hand)/2) * (self.tile_width + 2)
                y = hy
                self.draw_tile(x, y, tile, tag=f"{pos.name}_hand_{i}")

            # 显示风位
            self.canvas.create_text(hx, hy + 50, text=pos.name, fill="white", font=("Arial", 14, "bold"))
        self.canvas.update()

    def draw_tile(self, x, y, tile, tag=None):
        # 矩形+牌面文字
        rect = self.canvas.create_rectangle(x, y, x + self.tile_width, y + self.tile_height, fill="white")
        text = self.canvas.create_text(x + self.tile_width/2, y + self.tile_height/2, text=str(tile), font=("Arial", 14))
        if tag:
            self.canvas.tag_bind(rect, "<Button-1>", lambda e, t=tag: self.on_tile_click(t))
            self.canvas.tag_bind(text, "<Button-1>", lambda e, t=tag: self.on_tile_click(t))

    def on_tile_click(self, tag):
        # 处理玩家点击牌
        print(f"玩家点击: {tag}")
        # 实际应用时根据tag来获取具体是哪张牌（例如"EAST_hand_2"）
        # 你可以在这里实现选择出牌/定缺/换三张的逻辑
        self.selected_tiles.append(tag)
        # 你可以让选择够3张后自动返回结果/关闭窗口

    def ask_select_tiles(self, msg, num_required=1):
        # 显示提示，等待玩家选择num_required张牌
        self.selected_tiles = []
        messagebox.showinfo("选择", msg)
        self.draw_table()
        self.root.wait_variable(tk.BooleanVar()) # 你可以用变量通知主线程继续
        return self.selected_tiles[:num_required]

    def mainloop(self):
        self.draw_table()
        self.root.mainloop()

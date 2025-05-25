import tkinter as tk
from PIL import Image, ImageTk
from core.player import WindPosition
import os
from PIL import ImageEnhance

class MahjongTableUI(tk.Tk):
    def __init__(self, board, agents, human_pos, tile_img_dir="tiles", bg_img_path="images/table_bg.png"):
        super().__init__()
        self.title("麻将桌")
        self.geometry("1600x1200")
        self.canvas = tk.Canvas(self, width=1600, height=1200, bg="#136f20", highlightthickness=0)
        self.canvas.pack()
        self.bg_img = None
        # 支持自定义桌布背景图片
        if bg_img_path and os.path.exists(bg_img_path):
            bg_img = Image.open(bg_img_path).resize((1600, 1200))
            # 让背景更暗
            enhancer = ImageEnhance.Brightness(bg_img)
            bg_img = enhancer.enhance(0.7)  # 0.7倍亮度
            self.bg_img = ImageTk.PhotoImage(bg_img)

        self.board = board
        self.agents = agents
        self.human_pos = human_pos   # 当前操作者风位（会随局面更新）
        self.selected = []
        self.current_prompt = ""
        self.tile_imgs = {}    # 加载所有牌面图片（不含旋转）
        self.tile_imgs_rot = {}  # 加载所有旋转图片
        self.tile_img_dir = tile_img_dir
        self.load_tile_images()

        self.bottom_frame = tk.Frame(self, bg="#136f20")
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=6)
        self.prompt_label = tk.Label(self.bottom_frame, text="", font=("微软雅黑", 16, "bold"), bg="#136f20", fg="#FFD700")
        self.prompt_label.pack(side=tk.TOP, pady=2)
        self.ok_btn = tk.Button(self.bottom_frame, text="确定", command=self.submit_choice, font=("微软雅黑", 12))
        self.ok_btn.pack(side=tk.TOP, pady=2)
        self.custom_btns = []


        self.max_choice = 1
        self.on_choice_callback = None

    # 加载图片时支持多种tile名，旋转图片一起缓存
    def load_tile_images(self):
        for suit in ["man", "pin", "sou"]:
            for v in range(1, 10):
                # 1man.png or man1.png
                for name in [f"{v}{suit}", f"{suit}{v}"]:
                    path = f"{self.tile_img_dir}/{name}.png"
                    if os.path.exists(path):
                        img = Image.open(path).resize((44, 66))
                        self.tile_imgs[f"{v}{suit}"] = ImageTk.PhotoImage(img)
                        # 顺时针90度
                        img_cw = img.rotate(-90, expand=True)
                        self.tile_imgs_rot[f"{v}{suit}_cw"] = ImageTk.PhotoImage(img_cw)
                        # 逆时针90度
                        img_ccw = img.rotate(90, expand=True)
                        self.tile_imgs_rot[f"{v}{suit}_ccw"] = ImageTk.PhotoImage(img_ccw)
                        break

    def get_tile_img(self, tile):
        return self.tile_imgs.get(str(tile), None)

    def get_tile_img_rotated(self, tile, clockwise=True):
        key = str(tile) + ("_cw" if clockwise else "_ccw")
        return self.tile_imgs_rot.get(key, None)

    def draw_table(self):
        self.canvas.delete("all")
        if self.bg_img:
            self.canvas.create_image(0, 0, image=self.bg_img, anchor="nw")

        W, H = 1600, 1200
        side_margin = 130   # 边距大小，数值可根据实际窗口微调（100~200均可）
        hand_len = 14       # 每家最大手牌长度
        center_x, center_y = W // 2, H // 2
        tile_w, tile_h = 44, 66
        gap = 6                # 牌间距略大点更美观
        discard_row = 6        # 弃牌区每行/列最大数
        discard_y_center = center_y + 150  # 自己弃牌首行y
        discard_y_up = center_y - 150      # 对家弃牌首行y
        discard_x_left = center_x - 150    # 上家弃牌首行y
        discard_x_right = center_x + 150   # 下家弃牌首行y
        discard_row_gap = tile_h + 10     # 弃牌行高
        discard_col_gap = tile_w     # 弃牌列宽

        meld_y_down = H - 200
        meld_y_up = 200
        meld_x_left = 200
        meld_x_right = W - 200
        meld_group_gap = tile_w * 3.5
        meld_intra_gap = tile_w


        # 四家风位按东南西北顺时针
        wind_order = [WindPosition.EAST, WindPosition.SOUTH, WindPosition.WEST, WindPosition.NORTH]
        my_idx = wind_order.index(self.human_pos)
        # 动态映射界面四方
        ui_pos_list = ['DOWN', 'RIGHT', 'UP', 'LEFT']
        wind_to_ui = {wind_order[(my_idx + i) % 4]: ui_pos_list[i] for i in range(4)}
        ui_pos_to_wind = {v: k for k, v in wind_to_ui.items()}

        # 获取四家手牌
        hands = {pos: self.board.get_hand(self.agents[pos].position) for pos in wind_order}

        # 横排总宽
        total_width = tile_w * hand_len + gap * (hand_len - 1)
        start_x = (W - total_width) // 2

        # 竖排总高
        total_height = tile_w * hand_len + gap * (hand_len - 1)
        start_y = (H - total_height) // 2

        for pos in wind_order:
            hand = hands[pos]
            ui_pos = wind_to_ui[pos]
            if ui_pos == 'DOWN':
                # 当前操作者始终在下方
                for i, tile in enumerate(sorted(hand)):
                    img = self.get_tile_img(tile)
                    x = start_x + i * (tile_w + gap)
                    y = H - side_margin
                    pick = (i, str(tile))
                    offset = tile_h // 2 if pick in self.choice_tiles else 0
                    if img:
                        self.canvas.create_image(x, y + offset, image=img, anchor="s", tags=("DOWN", i, str(tile)))
                    else:
                        self.canvas.create_rectangle(x, y + offset - tile_h, x + tile_w, y + offset, fill="white")
                        self.canvas.create_text(x + tile_w//2, y + offset - tile_h//2, text=str(tile), font=("Arial", 12))
            elif ui_pos == 'UP':
                # 上方（对家）
                for i, tile in enumerate(sorted(hand)):
                    img = self.get_tile_img(tile)
                    x = start_x + i * (tile_w + gap)
                    y = side_margin
                    offset = -tile_h // 2 if str(tile) in self.choice_tiles else 0
                    if img:
                        self.canvas.create_image(x, y + offset, image=img, anchor="n", tags=("UP", i, str(tile)))
                    else:
                        self.canvas.create_rectangle(x, y + offset, x + tile_w, y + tile_h + offset, fill="white")
                        self.canvas.create_text(x + tile_w//2, y + tile_h//2 + offset, text=str(tile), font=("Arial", 12))
            elif ui_pos == 'LEFT':
                # 左侧，竖排从上到下，牌头朝右（顺时针90度），逆序
                for i, tile in enumerate(sorted(hand, reverse=True)):
                    img = self.get_tile_img_rotated(tile, clockwise=True)
                    x = side_margin
                    y = start_y + i * (tile_w + gap)
                    offset = -tile_w // 2 if str(tile) in self.choice_tiles else 0
                    if img:
                        self.canvas.create_image(x + offset, y, image=img, anchor="w", tags=("LEFT", i, str(tile)))
                    else:
                        self.canvas.create_rectangle(x + offset, y, x + tile_h + offset, y + tile_w, fill="white")
                        self.canvas.create_text(x + tile_h//2 + offset, y + tile_w//2, text=str(tile), font=("Arial", 12))
            elif ui_pos == 'RIGHT':
                # 右侧，竖排从下到上，牌头朝左（逆时针90度），正序
                for i, tile in enumerate(sorted(hand)):
                    img = self.get_tile_img_rotated(tile, clockwise=False)
                    x = W - side_margin
                    y = start_y + i * (tile_w + gap)
                    offset = tile_w // 2 if str(tile) in self.choice_tiles else 0
                    if img:
                        self.canvas.create_image(x + offset, y, image=img, anchor="e", tags=("RIGHT", i, str(tile)))
                    else:
                        self.canvas.create_rectangle(x + offset - tile_h, y, x + offset, y + tile_w, fill="white")
                        self.canvas.create_text(x + offset - tile_h//2, y + tile_w//2, text=str(tile), font=("Arial", 12))

        # 弃牌区
        # ---- DOWN（自己）：底部横排，左到右 ----
        down_discards = self.board.get_discards(ui_pos_to_wind['DOWN'])
        for i, tile in enumerate(down_discards):
            row = i // discard_row
            col = i % discard_row
            x = center_x - ((discard_row-1)/2)*(tile_w+gap) + col*(tile_w+gap)
            y = discard_y_center + row * discard_row_gap
            img = self.get_tile_img(tile)
            if img:
                self.canvas.create_image(x, y, image=img, anchor="n")

        # ---- UP（对家）：顶部横排，右到左 ----
        up_discards = self.board.get_discards(ui_pos_to_wind['UP'])
        for i, tile in enumerate(up_discards):
            row = i // discard_row
            col = i % discard_row
            x = center_x - ((discard_row-1)/2)*(tile_w+gap) + col*(tile_w+gap)
            y = discard_y_up - row * discard_row_gap
            img = self.get_tile_img(tile)
            if img:
                self.canvas.create_image(x, y, image=img, anchor="s")

        # ---- LEFT（左家）：左侧竖排，上到下 ----
        left_discards = self.board.get_discards(ui_pos_to_wind['LEFT'])
        for i, tile in enumerate(left_discards):
            col = i // discard_row
            row = i % discard_row
            x = discard_x_left - col * discard_col_gap
            y = center_y - ((discard_row-1)/2)*(tile_w) + row*(tile_w + gap)
            img = self.get_tile_img_rotated(tile, clockwise=True)
            if img:
                self.canvas.create_image(x, y, image=img, anchor="e")

        # ---- RIGHT（右家）：右侧竖排，上到下 ----
        right_discards = self.board.get_discards(ui_pos_to_wind['RIGHT'])
        for i, tile in enumerate(right_discards):
            col = i // discard_row
            row = i % discard_row
            x = discard_x_right + col * discard_col_gap
            y = center_y - ((discard_row-1)/2)*(tile_w) + row*(tile_w + gap)
            img = self.get_tile_img_rotated(tile, clockwise=False)
            if img:
                self.canvas.create_image(x, y, image=img, anchor="w")

        # ---- 副露区 ----
        down_melds = self.board.get_melds(ui_pos_to_wind['DOWN'])
        for i, meld in enumerate(down_melds):
            group_x = center_x - (len(down_melds)-1) * meld_group_gap / 2 + i*meld_group_gap
            for j, tile in enumerate(meld):
                x = group_x + j*meld_intra_gap + tile_w * (4 + len(down_melds))
                y = H - side_margin
                img = self.get_tile_img(tile)
                if img:
                    self.canvas.create_image(x, y, image=img, anchor="s")

        up_melds = self.board.get_melds(ui_pos_to_wind['UP'])
        for i, meld in enumerate(up_melds):
            group_x = center_x - (len(up_melds)-1) * meld_group_gap / 2 + i*meld_group_gap
            for j, tile in enumerate(meld):
                x = group_x + j*meld_intra_gap
                y = side_margin
                img = self.get_tile_img(tile)
                if img:
                    self.canvas.create_image(x, y, image=img, anchor="n")

        left_melds = self.board.get_melds(ui_pos_to_wind['LEFT'])
        for i, meld in enumerate(left_melds):
            group_y = center_y - (len(left_melds)-1) * meld_group_gap / 2 + i*meld_group_gap
            for j, tile in enumerate(meld):
                x = side_margin
                y = group_y + j*meld_intra_gap
                img = self.get_tile_img_rotated(tile, clockwise=True)
                if img:
                    self.canvas.create_image(x, y, image=img, anchor="w")

        right_melds = self.board.get_melds(ui_pos_to_wind['RIGHT'])
        for i, meld in enumerate(right_melds):
            group_y = center_y - (len(right_melds)-1) * meld_group_gap / 2 + i*meld_group_gap
            for j, tile in enumerate(meld):
                x = W - side_margin
                y = group_y + j*meld_intra_gap
                img = self.get_tile_img_rotated(tile, clockwise=False)
                if img:
                    self.canvas.create_image(x, y, image=img, anchor="e")

        # 中央剩余牌数
        self.canvas.create_text(W//2, H//2, text=f"剩余牌数：{len(self.board.wall)}", font=("微软雅黑", 24), fill="white")
        self.canvas.tag_bind("all", "<Button-1>", self.on_tile_click)

    def on_tile_click(self, event):
        items = self.canvas.find_withtag("current")
        if not items:
            return
        tags = self.canvas.gettags(items[0])
        if len(tags) < 3:
            return
        ui_pos = tags[0]
        if ui_pos != 'DOWN':
            return
        idx = int(tags[1])
        tile_str = tags[2]
        pick = (idx, tile_str)
        if pick in self.choice_tiles:
            self.choice_tiles.remove(pick)
        elif len(self.choice_tiles) < self.max_choice:
            self.choice_tiles.append(pick)
        self.draw_table()

    def ask_choice(self, prompt, max_choice=1, callback=None):
        self.clear_custom_btns()
        self.prompt_label.config(
            text=prompt, fg="#FFD700", font=("微软雅黑", 16, "bold")
        )
        self.choice_tiles = []
        self.max_choice = max_choice
        self.on_choice_callback = callback
        self.ok_btn.config(state=tk.NORMAL, text="确定")
        self.ok_btn.pack_forget()
        self.ok_btn.pack(side=tk.TOP, pady=2)
        self.prompt_label.pack_forget()
        self.prompt_label.pack(side=tk.TOP, pady=2)
        self.draw_table()

    def submit_choice(self):
        if len(self.choice_tiles) < self.max_choice:
            self.prompt_label.config(text=f"请再选{self.max_choice-len(self.choice_tiles)}张", fg="red")
            return
        if self.on_choice_callback:
            self.on_choice_callback(self.choice_tiles)

    def ask_missing_suit(self, callback=None):
        self.prompt_label.config(
            text="请选择定缺花色", fg="#FFD700", font=("微软雅黑", 16, "bold")
        )
        self.clear_custom_btns()
        suits = [("万", "man"), ("筒", "pin"), ("索", "sou")]
        def choose_suit(suit):
            self.clear_custom_btns()
            self.ok_btn.config(state=tk.DISABLED)
            if callback:
                callback(suit)
        for label, suit in suits:
            btn = tk.Button(
                self.bottom_frame, text=label, font=("微软雅黑", 18, "bold"),
                width=5, height=2, bg="#333", fg="#FFD700",
                command=lambda s=suit: choose_suit(s)
            )
            btn.pack(side=tk.LEFT, padx=40, pady=8)
            self.custom_btns.append(btn)
        self.ok_btn.config(state=tk.DISABLED)

    def clear_custom_btns(self):
        for btn in getattr(self, "custom_btns", []):
            btn.destroy()
        self.custom_btns = []

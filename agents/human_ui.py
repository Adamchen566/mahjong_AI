from typing import Optional, Tuple, List
from collections import Counter
from core.player import WindPosition
from core.tiles import Tile
from core.rules import can_win_standard

import tkinter as tk
from tkinter import simpledialog, messagebox

class HumanAgent:
    """
    适配Tkinter麻将桌UI的玩家代理：所有交互通过GUI而非input()。
    """
    def __init__(self, position: WindPosition, board, ui):
        self.position = position
        self.board = board
        self.ui = ui  # 必须传入MahjongTableUI实例
        self.missing_suit: Optional[str] = None

    def select_missing_suit(self) -> str:
        result = []
        def on_pick(suit):
            result.append(suit)
        self.ui.ask_missing_suit(callback=on_pick)
        while not result:
            self.ui.update()
        self.missing_suit = result[0]
        return result[0]

    def select_three_exchange(self):
        result = []
        def on_choice(choice):
            result.extend(choice)
        self.ui.ask_choice("请选择要换出的三张同花色牌", max_choice=3, callback=on_choice)
        while len(result) < 3:
            self.ui.update()
        hand = self.board.get_hand(self.position)
        hand_sorted = sorted(hand)
        selected_tiles = []
        for idx, tile_str in result:
            selected_tiles.append(hand_sorted[idx])
        return selected_tiles

    def choose_discard(self, drawn_tile=None):
        result = []
        def on_choice(tiles):
            result.extend(tiles)
            self.ui.prompt_label.config(text="")  # 清空提示
        self.ui.ask_choice("请选择要打出的牌", max_choice=1, callback=on_choice)
        while not result:
            self.ui.update()  # 让界面实时刷新
        hand = self.board.get_hand(self.position)
        hand_sorted = sorted(hand)
        idx, tile_str = result[0]
        return hand_sorted[idx]

    def decide_meld_action(self, last_tile: Tile) -> Optional[str]:
        """通过弹窗询问碰/杠决策"""
        hand = self.board.get_hand(self.position)
        count = hand.count(last_tile)
        action = None
        if count >= 3:
            if messagebox.askyesno("杠", f"是否要杠 {last_tile}?"):
                return 'kan'
        if count >= 2:
            if messagebox.askyesno("碰", f"是否要碰 {last_tile}?"):
                return 'pon'
        return None

    def decide_concealed_or_added_kan(self) -> Tuple[Optional[str], Optional[Tile]]:
        """通过弹窗询问暗杠或加杠"""
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        counts = Counter(hand)
        for tile, cnt in counts.items():
            if cnt == 4 and messagebox.askyesno("暗杠", f"是否暗杠 {tile}?"):
                return 'ankan', tile
        for meld in melds:
            if len(meld) == 3 and hand.count(meld[0]) >= 1:
                if messagebox.askyesno("加杠", f"是否加杠 {meld[0]}?"):
                    return 'chakan', meld[0]
        return None, None

    def can_win(self) -> bool:
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        return can_win_standard(hand, melds, None)

    def can_win_on_tile(self, tile: Tile) -> bool:
        hand = self.board.get_hand(self.position)
        melds = self.board.get_melds(self.position)
        return can_win_standard(hand, melds, tile)

    def decide_win(self, tile: Optional[Tile] = None) -> bool:
        """通过弹窗询问是否胡牌"""
        mode = '荣和' if tile is not None and tile not in self.board.get_hand(self.position) else '自摸'
        return messagebox.askyesno("胡牌", f"是否{mode}胡牌？")


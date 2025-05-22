import random
from typing import List, Dict
from core.tiles import Tile, generate_tile_set
from core.player import WindPosition

sichuan_tiles = generate_tile_set("chuan")      # 108张
nanjing_tiles = generate_tile_set("nanjing")    # 144张

class MahjongBoard:
    def __init__(self, rule: str = "chuan", dealer: WindPosition = WindPosition.EAST):
        self.wall: List[Tile] = generate_tile_set(rule)
        self.hands: Dict[WindPosition, List[Tile]] = {pos: [] for pos in WindPosition}
        self.melds: Dict[WindPosition, List[List[Tile]]] = {pos: [] for pos in WindPosition}
        self.discards: Dict[WindPosition, List[Tile]] = {pos: [] for pos in WindPosition}
        self.dealt_tiles: List[Tile] = []
        self.dealer: WindPosition = dealer
        self.rule = rule
        self.players = list(WindPosition)

    def shuffle_and_deal(self):
        random.shuffle(self.wall)
        for _ in range(13):
            for pos in WindPosition:
                tile = self.wall.pop()
                self.hands[pos].append(tile)
                self.dealt_tiles.append(tile)
        extra = self.wall.pop()
        self.hands[self.dealer].append(extra)
        self.dealt_tiles.append(extra)

    def draw_tile(self, pos: WindPosition) -> Tile:
        if not self.wall:
            raise ValueError("牌墙已空")
        tile = self.wall.pop()
        self.hands[pos].append(tile)
        self.dealt_tiles.append(tile)
        return tile

    def get_hand(self, pos: WindPosition) -> List[Tile]:
        return self.hands[pos]

    def get_all_hands(self) -> Dict[WindPosition, List[Tile]]:
        return self.hands

    def get_used_tiles(self) -> List[Tile]:
        return list(self.dealt_tiles)

    def is_tile_illegal(self, tile: Tile) -> bool:
        count = self.dealt_tiles.count(tile)
        if tile.suit.name == "FLOWER":
            return count > 1
        return count > 4

    def sort_hand(self, pos: WindPosition):
        self.hands[pos].sort()

    def sort_all_hands(self):
        for pos in WindPosition:
            self.sort_hand(pos)

    def discard_tile(self, pos: WindPosition, tile: Tile):
        if tile not in self.hands[pos]:
            raise ValueError(f"{tile} 不在 {pos.name} 的手牌中")
        self.hands[pos].remove(tile)
        self.discards[pos].append(tile)

    def is_draw(self) -> bool:
        return len(self.wall) == 0

    def get_melds(self, pos: WindPosition) -> List[List[Tile]]:
        return self.melds[pos]

    def add_meld(self, pos: WindPosition, tiles: List[Tile]):
        self.melds[pos].append(tiles)

    def remove_tiles(self, pos: WindPosition, tiles: List[Tile]):
        for t in tiles:
            if t in self.hands[pos]:
                self.hands[pos].remove(t)
            else:
                raise ValueError(f"{t} 不在 {pos.name} 的手牌中，无法执行副露操作")
            
    def get_discards(self, pos: WindPosition) -> List[Tile]:
        return self.discards[pos]

    def get_visible_tiles(self):
        tiles = []
        for player in self.players:
            tiles += self.get_discards(player)
            for meld in self.get_melds(player):
                tiles += meld
        return tiles

import numpy as np

class MahjongCounter:
    def __init__(self, n_channels=4):
        self.n_channels = n_channels
        # 定义牌索引（可根据你的项目自定义）
        self.tile_order = [
            '1man','2man','3man','4man','5man','6man','7man','8man','9man',
            '1pin','2pin','3pin','4pin','5pin','6pin','7pin','8pin','9pin',
            '1sou','2sou','3sou','4sou','5sou','6sou','7sou','8sou','9sou',
            'ew','sw','ww','nw',
            '1d','2d','3d',
            '1season','2season','3season','4season',
            '1flower','2flower','3flower','4flower'
        ]
        self.n_tiles = len(self.tile_order)
        self.counter = np.zeros((self.n_channels, self.n_tiles), dtype=int)
        self.tile2idx = {name: i for i, name in enumerate(self.tile_order)}
    
    def add(self, tile, channel=0, count=1):
        # 如果传入的是Tile对象而不是字符串，先转成标准牌名
        if not isinstance(tile, str):
            tile = f"{tile.value}{tile.suit.value}"
        idx = self.tile2idx[tile]
        self.counter[channel, idx] += count
    
    def remove(self, tile, channel=0, count=1):
        """ 移除某张牌（不会小于0）"""
        idx = self.tile2idx[tile]
        self.counter[channel, idx] = max(0, self.counter[channel, idx] - count)
    
    def get(self, tile, channel=0):
        """ 获取指定牌在某channel数量 """
        idx = self.tile2idx[tile]
        return self.counter[channel, idx]
    
    def reset(self):
        self.counter = np.zeros((self.n_channels, self.n_tiles), dtype=int)
    
    def get_counter(self):
        """ 返回完整计数矩阵 """
        return self.counter.copy()

    def to_flat(self):
        """ 转为一维特征用于AI分析 """
        return self.counter.flatten()
    
    def update_from_list(self, tile_list, channel=0):
        """ 用列表快速填充某channel（覆盖原有）"""
        self.counter[channel, :] = 0
        for tile in tile_list:
            idx = self.tile2idx[tile]
            self.counter[channel, idx] += 1

    def print_counter(self, label=""):
        print(f"\n== {label} ==" if label else "\n== 计数器 ==")
        for ch, name in enumerate(['手牌', '副露', '弃牌', '其它']):
            print(f"-- {name} --")
            row = self.counter[ch]
            tiles_str = [f"{self.tile_order[i]}:{row[i]}" for i in range(len(self.tile_order)) if row[i] > 0]
            print(", ".join(tiles_str) if tiles_str else "(空)")

    def fill_from_list(self, tiles, channel=0):
        self.counter[channel, :] = 0
        for t in tiles:
            self.add(t, channel)

            
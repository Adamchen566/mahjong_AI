"""把 ai.generate 生成的分片读进内存,按批取出来。

一个样本占 (71 + 16) × 27 字节,约 2.3 KB;400 万个样本约 9 GB,全部放内存。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List, NamedTuple, Optional, Sequence

import numpy as np

from chuanma.actions import NUM_ACTIONS

from .encoding import NUM_CHANNELS, ORACLE_CHANNELS


class Arrays(NamedTuple):
    obs: np.ndarray  # (n, 71, 27) uint8
    oracle: np.ndarray  # (n, 16, 27) uint8
    mask: np.ndarray  # (n, 115) bool
    action: np.ndarray  # (n,) int64
    ret: np.ndarray  # (n,) float32,原始分数


class Dataset:
    def __init__(self, dirs: Sequence[str], max_samples: Optional[int] = None) -> None:
        """dirs: 一个或多个 ai.generate 的输出目录。max_samples: 只读前这么多个(调试用)。"""
        shards: List[Path] = []
        total = 0
        for d in dirs:
            root = Path(d)
            meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
            if meta["obs_channels"] != NUM_CHANNELS or meta["oracle_channels"] != ORACLE_CHANNELS:
                raise ValueError(f"{d} 的编码格式和现在的代码对不上,要重新生成")
            found = sorted(root.glob("shard_*.npz"))
            if not found:
                raise FileNotFoundError(f"{d} 里没有分片")
            shards.extend(found)
            total += meta["samples"]
        n = min(total, max_samples) if max_samples else total

        self.obs = np.empty((n, NUM_CHANNELS, 27), dtype=np.uint8)
        self.oracle = np.empty((n, ORACLE_CHANNELS, 27), dtype=np.uint8)
        self.mask_bits = np.empty((n, 15), dtype=np.uint8)
        self.action = np.empty(n, dtype=np.uint8)
        self.ret = np.empty(n, dtype=np.int16)
        pos = 0
        for path in shards:
            if pos >= n:
                break
            with np.load(path) as z:
                k = min(len(z["action"]), n - pos)
                self.obs[pos : pos + k] = z["obs"][:k]
                self.oracle[pos : pos + k] = z["oracle"][:k]
                self.mask_bits[pos : pos + k] = z["mask"][:k]
                self.action[pos : pos + k] = z["action"][:k]
                self.ret[pos : pos + k] = z["ret"][:k]
                pos += k
        if pos != n:
            raise ValueError(f"meta.json 说有 {total} 个样本,实际只读到 {pos} 个")

    def __len__(self) -> int:
        return len(self.action)

    def take(self, idx: np.ndarray) -> Arrays:
        idx = np.sort(idx)  # 按地址顺序取,快一些;批内顺序无所谓
        mask = np.unpackbits(self.mask_bits[idx], axis=1)[:, :NUM_ACTIONS].astype(np.bool_)
        return Arrays(
            self.obs[idx],
            self.oracle[idx],
            mask,
            self.action[idx].astype(np.int64),
            self.ret[idx].astype(np.float32),
        )

    def batches(
        self, batch_size: int, shuffle: bool = True, seed: int = 0, drop_last: bool = False
    ) -> Iterator[Arrays]:
        n = len(self)
        order = np.random.default_rng(seed).permutation(n) if shuffle else np.arange(n)
        end = n - n % batch_size if drop_last else n
        for start in range(0, end, batch_size):
            yield self.take(order[start : start + batch_size])

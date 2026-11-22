"""把 riichi_ai.generate 生成的分片读进内存,按批取出来。

一个样本占 (80 + 17) × 34 字节,约 3.3 KB;300 万个样本约 10 GB,全部放内存。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List, NamedTuple, Optional, Sequence

import numpy as np

from riichi.actions import NUM_ACTIONS

from .encoding import NUM_CHANNELS, ORACLE_CHANNELS
from .generate import MASK_BYTES

N = 34


class Arrays(NamedTuple):
    obs: np.ndarray  # (n, 80, 34) uint8
    oracle: np.ndarray  # (n, 17, 34) uint8
    mask: np.ndarray  # (n, 119) bool
    action: np.ndarray  # (n,) int64
    ret: np.ndarray  # (n,) float32,名次分
    danger: np.ndarray  # (n, 34) float32
    has_danger: np.ndarray  # (n,) float32


class Dataset:
    def __init__(self, dirs: Sequence[str], max_samples: Optional[int] = None) -> None:
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
        self.obs = np.empty((n, NUM_CHANNELS, N), dtype=np.uint8)
        self.oracle = np.empty((n, ORACLE_CHANNELS, N), dtype=np.uint8)
        self.mask_bits = np.empty((n, MASK_BYTES), dtype=np.uint8)
        self.action = np.empty(n, dtype=np.uint8)
        self.ret = np.empty(n, dtype=np.float32)
        self.danger_bits = np.empty((n, 5), dtype=np.uint8)
        self.has_danger = np.empty(n, dtype=np.uint8)
        pos = 0
        for path in shards:
            if pos >= n:
                break
            with np.load(path) as z:
                k = min(len(z["action"]), n - pos)
                sl = slice(pos, pos + k)
                self.obs[sl] = z["obs"][:k]
                self.oracle[sl] = z["oracle"][:k]
                self.mask_bits[sl] = z["mask"][:k]
                self.action[sl] = z["action"][:k]
                self.ret[sl] = z["ret"][:k]
                self.danger_bits[sl] = z["danger"][:k]
                self.has_danger[sl] = z["has_danger"][:k]
                pos += k
        if pos != n:
            raise ValueError(f"meta.json 说有 {total} 个样本,实际只读到 {pos} 个")

    def __len__(self) -> int:
        return len(self.action)

    def take(self, idx: np.ndarray) -> Arrays:
        idx = np.sort(idx)
        mask = np.unpackbits(self.mask_bits[idx], axis=1)[:, :NUM_ACTIONS].astype(np.bool_)
        danger = np.unpackbits(self.danger_bits[idx], axis=1)[:, :N].astype(np.float32)
        return Arrays(
            self.obs[idx],
            self.oracle[idx],
            mask,
            self.action[idx].astype(np.int64),
            self.ret[idx],
            danger,
            self.has_danger[idx].astype(np.float32),
        )

    def batches(self, batch_size: int, shuffle: bool = True, seed: int = 0, drop_last: bool = False) -> Iterator[Arrays]:
        n = len(self)
        order = np.random.default_rng(seed).permutation(n) if shuffle else np.arange(n)
        end = n - n % batch_size if drop_last else n
        for start in range(0, end, batch_size):
            yield self.take(order[start : start + batch_size])

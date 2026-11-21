"""把训练出来的网络包成一个可以入座的策略。

它和人、规则型 AI 一样只拿到自己座位的 observation(),用 encode_obs() 编码,
所以看不到别人的手牌,也用不到网络里"看全场"的那一路。
"""
from __future__ import annotations

import os
import random
from functools import lru_cache
from typing import Any, Dict, List, Optional

import torch

from chuanma.actions import NUM_ACTIONS, Action

from .encoding import encode_obs
from .model import MahjongNet, load_model


@lru_cache(maxsize=8)
def _cached_model(path: str, mtime: float) -> MahjongNet:
    torch.set_num_threads(1)  # 一次只算一个局面,多线程反而慢;评估时还要开很多进程
    return load_model(path, "cpu")


class NetAgent:
    def __init__(self, path: str, seed: Optional[int] = None, greedy: bool = True) -> None:
        """path: 模型文件。greedy: 总是选概率最大的动作;否则按概率抽。"""
        self.path = path
        self.model = _cached_model(os.path.abspath(path), os.path.getmtime(path))
        self.greedy = greedy
        self.rng = random.Random(seed)

    @torch.no_grad()
    def probabilities(self, obs: Dict[str, Any], legal: List[Action]) -> List[float]:
        """每个合法动作的概率,顺序和 legal 一致。提示模式和复盘分析也用它。"""
        x = torch.from_numpy(encode_obs(obs)).unsqueeze(0)
        mask = torch.zeros(1, NUM_ACTIONS, dtype=torch.bool)
        ids = [a.id for a in legal]
        mask[0, ids] = True
        probs = torch.softmax(self.model(x, mask).logits[0], dim=0)
        return probs[ids].tolist()

    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action:
        if len(legal) == 1:
            return legal[0]
        probs = self.probabilities(obs, legal)
        if self.greedy:
            return legal[max(range(len(legal)), key=probs.__getitem__)]
        return self.rng.choices(legal, weights=probs)[0]

"""用网络给一批局面选动作。自我对弈采样和测速都用它。"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import torch

from .env import Batch
from .model import MahjongNet


@torch.no_grad()
def policy_step(
    model: MahjongNet, batch: Batch, device: torch.device, greedy: bool = False
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """返回 (动作, 动作的对数概率, 价值估计),都是长度为批大小的数组。

    批里带了全场信息(oracle)时,价值用看全场的那个头,否则用普通的价值头。
    """
    obs = torch.from_numpy(batch.obs).to(device)
    mask = torch.from_numpy(batch.mask).to(device)
    oracle = torch.from_numpy(batch.oracle).to(device) if batch.oracle is not None else None
    with torch.autocast(device.type, enabled=device.type == "cuda"):
        out = model(obs, mask, oracle)
    if greedy:
        action = out.logits.argmax(dim=1)
        logp = torch.zeros_like(out.value)
    else:
        dist = torch.distributions.Categorical(logits=out.logits)
        action = dist.sample()
        logp = dist.log_prob(action)
    value = out.oracle_value if out.oracle_value is not None else out.value
    return action.cpu().numpy(), logp.cpu().numpy(), value.cpu().numpy()

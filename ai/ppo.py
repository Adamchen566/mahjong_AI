"""PPO 的两块: 从轨迹算优势,和一次参数更新(阶段 4d)。

回报不折扣(一局很短,只关心最终得分)。分数一律除以 VALUE_SCALE,和价值头的单位一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F

from .env import Episode
from .model import VALUE_SCALE, MahjongNet


def gae(reward: np.ndarray, value: np.ndarray, lam: float = 0.95) -> Tuple[np.ndarray, np.ndarray]:
    """一条轨迹的优势和回报目标。终局之后的价值是 0。

    lam=1 时优势就是"实际拿到的 − 估计的";lam=0 时只看一步。中间值在方差和偏差之间折中。
    """
    t_max = len(reward)
    adv = np.empty(t_max, dtype=np.float32)
    next_value = 0.0
    running = 0.0
    for t in range(t_max - 1, -1, -1):
        delta = reward[t] + next_value - value[t]
        running = delta + lam * running
        adv[t] = running
        next_value = value[t]
    return adv, adv + value


@dataclass
class Rollout:
    obs: torch.Tensor  # (N, C, 27) uint8
    oracle: torch.Tensor  # (N, 16, 27) uint8
    mask: torch.Tensor  # (N, 115) bool
    action: torch.Tensor  # (N,) int64
    logp: torch.Tensor  # (N,) 采样时那个策略给的对数概率
    adv: torch.Tensor  # (N,)
    ret: torch.Tensor  # (N,) 价值头的学习目标

    def __len__(self) -> int:
        return len(self.action)


def build_rollout(episodes: Sequence[Episode], device: torch.device, lam: float = 0.95) -> Rollout:
    advs: List[np.ndarray] = []
    rets: List[np.ndarray] = []
    for ep in episodes:
        a, r = gae(ep.reward / VALUE_SCALE, ep.value, lam)
        advs.append(a)
        rets.append(r)

    def cat(parts: List[np.ndarray]) -> torch.Tensor:
        return torch.from_numpy(np.concatenate(parts)).to(device)

    return Rollout(
        obs=cat([e.obs for e in episodes]),
        oracle=cat([e.oracle for e in episodes]),
        mask=cat([e.mask for e in episodes]),
        action=cat([e.action for e in episodes]).long(),
        logp=cat([e.logp for e in episodes]),
        adv=cat(advs),
        ret=cat(rets),
    )


def explained_variance(pred: torch.Tensor, target: torch.Tensor) -> float:
    """价值估计解释了回报里多大比例的波动。1 是完美,0 等于瞎猜平均值。"""
    var = target.var()
    return float(1 - (target - pred).var() / var) if var > 0 else 0.0


def ppo_update(
    model: MahjongNet,
    opt: torch.optim.Optimizer,
    scaler: "torch.amp.GradScaler",
    data: Rollout,
    epochs: int = 2,
    batch_size: int = 4096,
    clip: float = 0.2,
    vf_coef: float = 0.5,
    ent_coef: float = 0.01,
    max_grad_norm: float = 1.0,
    target_kl: float = 0.03,
) -> Dict[str, float]:
    device = data.action.device
    use_amp = device.type == "cuda"
    n = len(data)
    adv = (data.adv - data.adv.mean()) / (data.adv.std() + 1e-8)
    value_pred = torch.zeros(n, device=device)
    oracle_pred = torch.zeros(n, device=device)
    sums: Dict[str, float] = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "kl": 0.0, "clip_frac": 0.0}
    steps = 0
    model.train()
    stop = False
    for epoch in range(epochs):
        order = torch.randperm(n, device=device)
        for start in range(0, n, batch_size):
            idx = order[start : start + batch_size]
            mask = data.mask[idx]
            with torch.autocast(device.type, enabled=use_amp):
                out = model(data.obs[idx], mask, data.oracle[idx])
            logp_all = F.log_softmax(out.logits, dim=1)
            logp = logp_all.gather(1, data.action[idx].unsqueeze(1)).squeeze(1)
            ratio = torch.exp(logp - data.logp[idx])
            a = adv[idx]
            policy_loss = -torch.min(ratio * a, ratio.clamp(1 - clip, 1 + clip) * a).mean()
            safe = logp_all.masked_fill(~mask, 0.0)  # 非法动作概率是 0,别让 0 × 负无穷变成 nan
            entropy = -(safe.exp() * safe * mask).sum(1).mean()
            target = data.ret[idx]
            value_loss = F.smooth_l1_loss(out.value, target) + F.smooth_l1_loss(out.oracle_value, target)
            loss = policy_loss + vf_coef * value_loss - ent_coef * entropy

            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            scaler.step(opt)
            scaler.update()

            with torch.no_grad():
                kl = (data.logp[idx] - logp).mean().item()
                if epoch == 0:
                    value_pred[idx] = out.value.detach()
                    oracle_pred[idx] = out.oracle_value.detach()
                sums["policy_loss"] += policy_loss.item()
                sums["value_loss"] += value_loss.item()
                sums["entropy"] += entropy.item()
                sums["kl"] += kl
                sums["clip_frac"] += ((ratio - 1).abs() > clip).float().mean().item()
            steps += 1
            if kl > target_kl and epoch > 0:  # 新旧策略已经差得够多,这批数据不宜再用
                stop = True
                break
        if stop:
            break
    model.eval()
    result = {k: v / steps for k, v in sums.items()}
    result["ev_value"] = explained_variance(value_pred, data.ret)
    result["ev_oracle"] = explained_variance(oracle_pred, data.ret)
    result["updates"] = steps
    return result

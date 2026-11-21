"""策略-价值网络(阶段 4c、4d 共用)。

输入   obs (B, 71, 27) uint8,见 ai/encoding.py
主干   一维残差卷积,沿 27 个牌位做卷积
输出   logits (B, 115)      策略头;给了掩码时非法动作是负无穷
       value (B,)           价值头: 从这个局面到终局还会得多少分(除以 VALUE_SCALE)
       oracle_value (B,)    看得到全场的价值头,只在给了 oracle 输入时才算

策略头和 value 只依赖 obs。oracle 输入只流进 oracle_value,所以上线时不带它也不影响出牌。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, NamedTuple, Optional, Union

import torch
import torch.nn.functional as F
from torch import nn

from chuanma.actions import NUM_ACTIONS

from .encoding import NUM_CHANNELS, OBS_SCALE, ORACLE_CHANNELS

VALUE_SCALE = 8.0  # 分数除以它再给价值头学;封顶 5 番时一次大的输赢是 32 分上下
N = 27


@dataclass(frozen=True)
class ModelConfig:
    channels: int = 128
    blocks: int = 10
    obs_channels: int = NUM_CHANNELS
    oracle_channels: int = ORACLE_CHANNELS
    head_channels: int = 32
    hidden: int = 256


class Output(NamedTuple):
    logits: torch.Tensor
    value: torch.Tensor
    oracle_value: Optional[torch.Tensor]


class ResBlock(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(channels, channels, 3, padding=1, bias=False)
        self.norm1 = nn.GroupNorm(8, channels)
        self.conv2 = nn.Conv1d(channels, channels, 3, padding=1, bias=False)
        self.norm2 = nn.GroupNorm(8, channels)
        nn.init.zeros_(self.norm2.weight)  # 每个残差块一开始等于恒等映射,深了也好训

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = F.relu(self.norm1(self.conv1(x)))
        y = self.norm2(self.conv2(y))
        return F.relu(x + y)


class Head(nn.Module):
    def __init__(self, in_channels: int, cfg: ModelConfig, out: int) -> None:
        super().__init__()
        self.conv = nn.Conv1d(in_channels, cfg.head_channels, 1)
        self.fc1 = nn.Linear(cfg.head_channels * N, cfg.hidden)
        self.fc2 = nn.Linear(cfg.hidden, out)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.conv(x)).flatten(1)
        return self.fc2(F.relu(self.fc1(x)))


class MahjongNet(nn.Module):
    def __init__(self, config: ModelConfig = ModelConfig()) -> None:
        super().__init__()
        self.config = config
        c = config.channels
        self.register_buffer("obs_scale", torch.from_numpy(OBS_SCALE).view(1, -1, 1), persistent=False)
        self.stem = nn.Sequential(
            nn.Conv1d(config.obs_channels, c, 3, padding=1, bias=False), nn.GroupNorm(8, c), nn.ReLU()
        )
        self.trunk = nn.Sequential(*[ResBlock(c) for _ in range(config.blocks)])
        self.policy_head = Head(c, config, NUM_ACTIONS)
        self.value_head = Head(c, config, 1)
        # 全场信息这一路: 单独编码别人的手牌和牌墙,再和主干的特征拼起来
        oc = c // 2
        self.oracle_stem = nn.Sequential(
            nn.Conv1d(config.oracle_channels, oc, 3, padding=1, bias=False),
            nn.GroupNorm(8, oc),
            nn.ReLU(),
            ResBlock(oc),
            ResBlock(oc),
        )
        self.oracle_head = Head(c + oc, config, 1)

    def forward(
        self,
        obs: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
        oracle: Optional[torch.Tensor] = None,
    ) -> Output:
        x = obs.float() * self.obs_scale
        feat = self.trunk(self.stem(x))
        logits = self.policy_head(feat).float()
        if mask is not None:
            logits = logits.masked_fill(~mask, float("-inf"))
        value = self.value_head(feat).float().squeeze(1)
        oracle_value = None
        if oracle is not None:
            o = self.oracle_stem(oracle.float())
            oracle_value = self.oracle_head(torch.cat([feat, o], dim=1)).float().squeeze(1)
        return Output(logits, value, oracle_value)

    def num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())


def save_checkpoint(path: Union[str, Path], model: MahjongNet, **extra: Any) -> None:
    """存模型。extra 里放训练步数、成绩之类的附带信息。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {"config": asdict(model.config), "model": model.state_dict(), **extra}
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, tmp)
    tmp.replace(path)  # 先写临时文件再改名,中途断电不会留下半个文件


def load_checkpoint(path: Union[str, Path], device: Union[str, torch.device] = "cpu") -> Dict[str, Any]:
    return torch.load(path, map_location=device, weights_only=False)


def load_model(path: Union[str, Path], device: Union[str, torch.device] = "cpu") -> MahjongNet:
    payload = load_checkpoint(path, device)
    model = MahjongNet(ModelConfig(**payload["config"]))
    model.load_state_dict(payload["model"])
    return model.to(device).eval()

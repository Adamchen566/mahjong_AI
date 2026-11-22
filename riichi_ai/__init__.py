"""riichi_ai: 日麻的训练和模型。结构照川麻的 ai/,两边互不依赖。

| 模块 | 内容 |
|---|---|
| encoding | 局面编码、看全场的额外输入、点炮标签 |
| env | 训练用的并行对局环境(一条轨迹是一个座位的一整场半庄) |
| generate / dataset | 模仿学习的数据 |
| model | 策略-价值网络,另带点炮头 |
| train_bc / ppo / train_ppo | 模仿学习、自我对弈 |
| evaluate / ladder | 同牌对比评估、段位梯 |
| export / onnx_agent | 导出 ONNX、对局软件里入座和提示 |
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from riichi.agents import Agent, RandomAgent, ShantenAgent, SimpleAgent


def _net(seed: Optional[int] = None) -> Agent:
    from .onnx_agent import OnnxAgent  # 用到时才导入 onnxruntime

    return OnnxAgent(seed=seed)


AGENTS: Dict[str, Callable[..., Agent]] = {
    "random": RandomAgent,
    "simple": SimpleAgent,
    "shanten": ShantenAgent,
    "net": _net,  # 训练出的模型,文件在 models/riichi.onnx
}

AGENT_LABELS: Dict[str, str] = {
    "random": "随机",
    "simple": "简单",
    "shanten": "规则型",
    "net": "神经网络",
}


def make_agent(name: str, seed: Optional[int] = None) -> Agent:
    """name 是登记表里的名字,或者一个模型文件(.pt 或 .onnx)的路径。"""
    if name in AGENTS:
        return AGENTS[name](seed)
    if name.endswith(".pt"):
        from .net_agent import NetAgent

        return NetAgent(name, seed)
    if name.endswith(".onnx"):
        from .onnx_agent import OnnxAgent

        return OnnxAgent(name, seed)
    raise ValueError(f"未知的策略 {name!r},可选: {sorted(AGENTS)},或一个 .pt / .onnx 模型文件")


__all__ = ["AGENTS", "AGENT_LABELS", "make_agent"]

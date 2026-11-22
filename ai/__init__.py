"""ai: 建在规则引擎之上的各种策略,以及评估工具。"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from chuanma.agents import Agent, RandomAgent, SimpleAgent

from .rule_agent import RuleAgent

def _net(seed: Optional[int] = None) -> Agent:
    from .onnx_agent import OnnxAgent  # 用到时才导入 onnxruntime

    return OnnxAgent(seed=seed)


# 名字 -> 策略类。界面的难度选项和评估工具都从这里取
AGENTS: Dict[str, Callable[..., Agent]] = {
    "random": RandomAgent,
    "simple": SimpleAgent,
    "rule": RuleAgent,
    "net": _net,  # 训练出的模型,文件在 models/chuanma.onnx
}

AGENT_LABELS: Dict[str, str] = {
    "random": "随机",
    "simple": "简单",
    "rule": "规则型",
    "net": "神经网络",
}


def make_agent(name: str, seed: Optional[int] = None) -> Agent:
    """name 是登记表里的名字,或者一个模型文件(.pt 或 .onnx)的路径。"""
    if name in AGENTS:
        return AGENTS[name](seed)
    if name.endswith(".pt"):
        from .net_agent import NetAgent  # 用到模型时才导入 torch,对局软件不必装它

        return NetAgent(name, seed)
    if name.endswith(".onnx"):
        from .onnx_agent import OnnxAgent

        return OnnxAgent(name, seed)
    raise ValueError(f"未知的策略 {name!r},可选: {sorted(AGENTS)},或一个 .pt / .onnx 模型文件")


__all__ = ["AGENTS", "AGENT_LABELS", "RuleAgent", "make_agent"]

"""ai: 建在规则引擎之上的各种策略,以及评估工具。"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from chuanma.agents import Agent, RandomAgent, SimpleAgent

from .rule_agent import RuleAgent

# 名字 -> 策略类。界面的难度选项和评估工具都从这里取
AGENTS: Dict[str, Callable[..., Agent]] = {
    "random": RandomAgent,
    "simple": SimpleAgent,
    "rule": RuleAgent,
}

AGENT_LABELS: Dict[str, str] = {
    "random": "随机",
    "simple": "简单",
    "rule": "规则型",
}


def make_agent(name: str, seed: Optional[int] = None) -> Agent:
    try:
        return AGENTS[name](seed)
    except KeyError:
        raise ValueError(f"未知的策略 {name!r},可选: {sorted(AGENTS)}") from None


__all__ = ["AGENTS", "AGENT_LABELS", "RuleAgent", "make_agent"]

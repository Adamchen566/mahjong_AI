"""riichi: 日本麻将(立直麻将,四人)规则引擎。

没有界面、不打印、不联网,给定种子完全可复现。规则范围见 docs/riichi-rules.md。
"""
from .actions import NUM_ACTIONS, Action, ActionType
from .agents import Agent, RandomAgent, ShantenAgent, SimpleAgent, make_agent
from .config import RuleConfig
from .game import Game, IllegalAction, Phase
from .record import GameRecord, replay
from .runner import play_game, simulate
from .scoring import HandValue, Meld, MeldType, WinContext, evaluate

__version__ = "0.1.0"

__all__ = [
    "Action",
    "ActionType",
    "Agent",
    "Game",
    "GameRecord",
    "HandValue",
    "IllegalAction",
    "Meld",
    "MeldType",
    "NUM_ACTIONS",
    "Phase",
    "RandomAgent",
    "RuleConfig",
    "ShantenAgent",
    "SimpleAgent",
    "WinContext",
    "evaluate",
    "make_agent",
    "play_game",
    "replay",
    "simulate",
]

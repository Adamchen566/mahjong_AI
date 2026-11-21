"""chuanma: 四川麻将(血战到底)规则引擎。

没有界面、不打印、不联网,给定种子完全可复现。
界面、训练环境、AI 都建在它上面。入口见 game.Game。
"""
from .actions import NUM_ACTIONS, Action, ActionType
from .agents import Agent, RandomAgent, SimpleAgent
from .config import RuleConfig
from .fan import FanResult, Meld, MeldType, WinContext, evaluate_fan
from .game import Game, IllegalAction, Phase, Transfer, WinRecord
from .record import GameRecord, replay
from .runner import play_game, simulate

__version__ = "0.1.0"

__all__ = [
    "Action",
    "ActionType",
    "Agent",
    "FanResult",
    "Game",
    "GameRecord",
    "IllegalAction",
    "Meld",
    "MeldType",
    "NUM_ACTIONS",
    "Phase",
    "RandomAgent",
    "RuleConfig",
    "SimpleAgent",
    "Transfer",
    "WinContext",
    "WinRecord",
    "evaluate_fan",
    "play_game",
    "replay",
    "simulate",
]

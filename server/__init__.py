"""server: 本机运行的对局服务(阶段 2)。入口是 python -m server。"""
from .app import create_app
from .match import Match

__all__ = ["Match", "create_app"]

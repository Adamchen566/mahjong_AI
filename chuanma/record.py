"""牌谱: 用 配置 + 种子(或牌墙)+ 动作序列 就能完整重现一局。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .config import RuleConfig
from .game import Game

RECORD_VERSION = 1


@dataclass
class GameRecord:
    config: Dict[str, Any]
    seed: Optional[int]
    dealer: int
    exchange_direction: int
    actions: List[int]
    wall: Optional[List[int]] = None  # 只有自定义牌墙时才保存
    scores: Optional[List[int]] = None  # 结束时的分数,用于复盘校验
    version: int = RECORD_VERSION
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_game(cls, game: Game, meta: Optional[Dict[str, Any]] = None) -> "GameRecord":
        return cls(
            config=game.config.to_dict(),
            seed=game.seed,
            dealer=game.dealer,
            exchange_direction=game.exchange_direction,
            actions=list(game.history),
            wall=list(game.wall) if game.custom_wall or game.seed is None else None,
            scores=list(game.scores) if game.is_over else None,
            meta=dict(meta or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "config": self.config,
            "seed": self.seed,
            "dealer": self.dealer,
            "exchange_direction": self.exchange_direction,
            "wall": self.wall,
            "actions": self.actions,
            "scores": self.scores,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameRecord":
        if data.get("version") != RECORD_VERSION:
            raise ValueError(f"不支持的牌谱版本: {data.get('version')}")
        return cls(
            config=data["config"],
            seed=data["seed"],
            dealer=data["dealer"],
            exchange_direction=data["exchange_direction"],
            actions=list(data["actions"]),
            wall=data.get("wall"),
            scores=data.get("scores"),
            meta=data.get("meta") or {},
        )

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "GameRecord":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def replay(record: GameRecord, upto: Optional[int] = None, record_events: bool = True) -> Game:
    """按牌谱重放,返回重放后的 Game。upto 指定只放前多少步。

    放完全部动作且牌谱里存了分数时,会校验分数是否一致。
    """
    game = Game(
        config=RuleConfig.from_dict(record.config),
        seed=record.seed,
        dealer=record.dealer,
        wall=record.wall,
        exchange_direction=record.exchange_direction,
        record_events=record_events,
    )
    actions = record.actions if upto is None else record.actions[:upto]
    for action_id in actions:
        game.step(action_id)
    if upto is None and record.scores is not None and game.is_over:
        if game.scores != record.scores:
            raise ValueError(f"复盘分数不一致: 牌谱 {record.scores}, 重放 {game.scores}")
    return game

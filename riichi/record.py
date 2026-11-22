"""牌谱: 配置 + 种子(或牌墙)+ 动作序列 就能完整重现一场。"""
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
    actions: List[int]
    walls: Optional[List[List[int]]] = None  # 只有自定义牌墙或没有种子时才保存
    scores: Optional[List[int]] = None
    version: int = RECORD_VERSION
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_game(cls, game: Game, meta: Optional[Dict[str, Any]] = None) -> "GameRecord":
        keep_walls = bool(game.custom_walls) or game.seed is None
        return cls(
            config=game.config.to_dict(),
            seed=game.seed,
            actions=list(game.history),
            walls=[list(w) for w in game.walls_used] if keep_walls else None,
            scores=list(game.scores) if game.is_over else None,
            meta=dict(meta or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "game": "riichi",
            "config": self.config,
            "seed": self.seed,
            "walls": self.walls,
            "actions": self.actions,
            "scores": self.scores,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameRecord":
        if data.get("version") != RECORD_VERSION or data.get("game") != "riichi":
            raise ValueError("不是这个版本的日麻牌谱")
        return cls(
            config=data["config"],
            seed=data["seed"],
            actions=list(data["actions"]),
            walls=data.get("walls"),
            scores=data.get("scores"),
            meta=data.get("meta") or {},
        )

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "GameRecord":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def replay(record: GameRecord, upto: Optional[int] = None, record_events: bool = True) -> Game:
    """按牌谱重放。放完全部动作且牌谱里存了点数时会核对。"""
    game = Game(
        config=RuleConfig.from_dict(record.config),
        seed=record.seed,
        walls=record.walls,
        record_events=record_events,
    )
    acts = record.actions if upto is None else record.actions[:upto]
    for a in acts:
        game.step(a)
    if upto is None and record.scores is not None and game.is_over and game.scores != record.scores:
        raise ValueError(f"复盘点数不一致: 牌谱 {record.scores}, 重放 {game.scores}")
    return game

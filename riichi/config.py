"""规则配置。默认值是天凤段位战(四人、喰断有、赤有、半庄),见 docs/riichi-rules.md。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class RuleConfig:
    length: str = "hanchan"  # "hanchan" 半庄;"tonpu" 东风战;"one" 只打一局(测试用)
    start_points: int = 25000
    target_points: int = 30000  # 返点: 到这个点数才能正常结束,也是名次分的基准
    uma: Tuple[int, int, int, int] = (20, 10, -10, -20)  # 顺位马,一位到四位
    aka: bool = True  # 赤宝牌
    kuitan: bool = True  # 喰断: 副露的断幺九
    nagashi_mangan: bool = True  # 流局满贯
    abortive_draws: bool = True  # 九种九牌、四风连打、四杠散了、四家立直、三家和
    tobi: bool = True  # 击飞: 有人低于 0 分时整场结束
    pao: bool = True  # 大三元、大四喜的包牌
    kazoe: bool = True  # 数役满(关掉则 13 番以上按三倍满)

    def __post_init__(self) -> None:
        if self.length not in ("hanchan", "tonpu", "one"):
            raise ValueError(f"length 只能是 hanchan / tonpu / one: {self.length!r}")
        if len(self.uma) != 4 or sum(self.uma) != 0:
            raise ValueError("uma 必须是 4 个数且合计为 0")
        object.__setattr__(self, "uma", tuple(self.uma))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["uma"] = list(self.uma)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuleConfig":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

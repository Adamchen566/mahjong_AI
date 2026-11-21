"""规则配置。各地川麻细则不同,凡是有分歧的地方都做成开关,默认值见 docs/rules.md。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict

ZIMO_MODES = ("jia_di", "jia_fan", "none")


@dataclass(frozen=True)
class RuleConfig:
    # --- 基础 ---
    base_score: int = 1  # 底分
    max_fan: int = 5  # 封顶番数,胡牌得分 = 底分 * 2^min(番数, 封顶)

    # --- 流程 ---
    exchange_three: bool = True  # 是否换三张(必须同花色)

    # --- 胡牌计分 ---
    # 自摸: "jia_di" 每家多付 1 个底分; "jia_fan" 多算 1 番; "none" 不加
    zimo_mode: str = "jia_di"
    men_qing_zhong_zhang: bool = True  # 是否计 门清(+1) 和 中张/断幺九(+1)
    tian_di_hu: bool = True  # 是否计 天胡/地胡
    haidi: bool = True  # 是否计 海底捞月/海底炮

    # --- 杠分(刮风下雨),单位是底分 ---
    an_gang_score: int = 2  # 暗杠: 其余未胡玩家每人付
    jia_gang_score: int = 1  # 加杠(补杠): 其余未胡玩家每人付
    ming_gang_score: int = 2  # 直杠(点杠): 放杠者一人付

    # --- 流局结算 ---
    cha_hua_zhu: bool = True  # 查花猪
    cha_da_jiao: bool = True  # 查大叫
    tui_shui: bool = True  # 退税(无叫玩家退回杠分)

    def __post_init__(self) -> None:
        if self.base_score <= 0:
            raise ValueError("base_score 必须为正")
        if self.max_fan < 0:
            raise ValueError("max_fan 不能为负")
        if self.zimo_mode not in ZIMO_MODES:
            raise ValueError(f"zimo_mode 必须是 {ZIMO_MODES} 之一")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuleConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"未知的配置项: {sorted(unknown)}")
        return cls(**data)

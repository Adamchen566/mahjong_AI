"""用 onnxruntime 在 CPU 上跑导出的日麻模型。对局软件里的"神经网络"对手、提示、点炮概率和复盘分析都用它。

和人、规则型策略一样,它只拿到自己座位的 observation(),用 encode_obs() 编码。
"""
from __future__ import annotations

import os
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from riichi.actions import Action

from .encoding import NUM_CHANNELS, encode_obs

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "riichi.onnx"
VALUE_SCALE = 20.0  # 和 riichi_ai.model.VALUE_SCALE 一致;这里不导入,免得对局软件要装 torch


def model_status(path: Optional[os.PathLike] = None) -> Tuple[bool, str]:
    path = Path(path or DEFAULT_MODEL)
    if not path.is_file():
        return False, f"找不到模型文件 {path.name}"
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False, "没有安装 onnxruntime"
    return True, ""


@lru_cache(maxsize=4)
def _session(path: str, mtime: float):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
    shape = session.get_inputs()[0].shape
    if shape[1] != NUM_CHANNELS:
        raise ValueError(f"模型的输入是 {shape[1]} 个通道,现在的编码是 {NUM_CHANNELS} 个,要重新导出")
    return session


class OnnxAgent:
    def __init__(self, path: Optional[os.PathLike] = None, seed: Optional[int] = None, greedy: bool = True) -> None:
        self.path = str(path or DEFAULT_MODEL)
        self.session = _session(os.path.abspath(self.path), os.path.getmtime(self.path))
        self.greedy = greedy
        self.rng = random.Random(seed)

    def evaluate(self, obs: Dict[str, Any], legal: List[Action]) -> Tuple[List[float], float, List[float]]:
        """(每个合法动作的概率,顺序同 legal;局面估值,单位是名次分;34 种牌各自打出去被荣和的概率)。"""
        x = encode_obs(obs)[None]
        logits, value, danger = self.session.run(None, {"obs": x})
        z = logits[0][[a.id for a in legal]].astype(np.float64)
        z -= z.max()
        p = np.exp(z)
        p /= p.sum()
        return p.tolist(), float(value[0]) * VALUE_SCALE, danger[0].astype(float).tolist()

    def probabilities(self, obs: Dict[str, Any], legal: List[Action]) -> List[float]:
        return self.evaluate(obs, legal)[0]

    def act(self, obs: Dict[str, Any], legal: List[Action]) -> Action:
        if len(legal) == 1:
            return legal[0]
        probs = self.probabilities(obs, legal)
        if self.greedy:
            return legal[max(range(len(legal)), key=probs.__getitem__)]
        return self.rng.choices(legal, weights=probs)[0]

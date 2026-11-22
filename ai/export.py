"""把训练出的模型导出成 ONNX,给对局软件用。

    python -m ai.export --checkpoint checkpoints/ppo/best.pt --out models/chuanma.onnx

导出的只有出牌要用的部分: 输入 obs (B, 71, 27) uint8,输出 logits (B, 115) 和 value (B,)。
"看全场"的那一路不导出,所以入座的模型结构上就接触不到别人的手牌。
对局软件用 onnxruntime 在 CPU 上推理,不需要装 PyTorch。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import torch
from torch import nn

from .encoding import NUM_CHANNELS
from .model import MahjongNet, load_checkpoint, load_model


class _Deploy(nn.Module):
    def __init__(self, model: MahjongNet) -> None:
        super().__init__()
        self.model = model

    def forward(self, obs: torch.Tensor):
        out = self.model(obs)
        return out.logits, out.value


def export_onnx(checkpoint: str, out_path: str, note: str = "") -> Path:
    model = load_model(checkpoint, "cpu")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, NUM_CHANNELS, 27, dtype=torch.uint8)
    torch.onnx.export(
        _Deploy(model).eval(),
        (dummy,),
        str(out),
        input_names=["obs"],
        output_names=["logits", "value"],
        dynamic_axes={"obs": {0: "batch"}, "logits": {0: "batch"}, "value": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    payload = load_checkpoint(checkpoint)
    meta = {
        "source": str(checkpoint),
        "stage": payload.get("stage", ""),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "obs_channels": NUM_CHANNELS,
        "parameters": model.num_parameters(),
        "note": note,
    }
    out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ai.export", description="导出 ONNX 模型")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", default="models/chuanma.onnx")
    parser.add_argument("--note", default="", help="写进旁边 .json 里的说明,比如成绩")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    out = export_onnx(args.checkpoint, args.out, args.note)
    print(f"已导出 {out}({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

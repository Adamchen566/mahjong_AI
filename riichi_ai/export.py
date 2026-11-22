"""把日麻模型导出成 ONNX,给对局软件用。

    python -m riichi_ai.export --checkpoint checkpoints/riichi_ppo/best.pt --out models/riichi.onnx

导出的部分: 输入 obs (B, 80, 34) uint8,输出 logits (B, 119)、value (B,)、danger (B, 34)。
"看全场"的那一路不导出,所以入座的模型结构上就接触不到别人的手牌。
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
from .model import RiichiNet, load_checkpoint, load_model


class _Deploy(nn.Module):
    def __init__(self, model: RiichiNet) -> None:
        super().__init__()
        self.model = model

    def forward(self, obs: torch.Tensor):
        out = self.model(obs)
        return out.logits, out.value, torch.sigmoid(out.danger)


def export_onnx(checkpoint: str, out_path: str, note: str = "") -> Path:
    model = load_model(checkpoint, "cpu")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, NUM_CHANNELS, 34, dtype=torch.uint8)
    torch.onnx.export(
        _Deploy(model).eval(),
        (dummy,),
        str(out),
        input_names=["obs"],
        output_names=["logits", "value", "danger"],
        dynamic_axes={k: {0: "batch"} for k in ("obs", "logits", "value", "danger")},
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
    parser = argparse.ArgumentParser(prog="python -m riichi_ai.export", description="导出日麻 ONNX 模型")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", default="models/riichi.onnx")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    out = export_onnx(args.checkpoint, args.out, args.note)
    print(f"已导出 {out}({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

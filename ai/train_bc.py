"""模仿学习(阶段 4c): 让网络学规则型 AI 的选择。

    python -m ai.train_bc --data data/bc_rule/clean data/bc_rule/explore --val data/bc_rule_val --out checkpoints/bc

损失 = 策略交叉熵 + value_weight × (价值头 + 看全场的价值头 的回归误差)。
每隔一段在验证集上算"和老师选同一步的比例",存 latest.pt;比例创新高时另存 best.pt。
"""
from __future__ import annotations

import argparse
import csv
import math
import queue
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import numpy as np
import torch
import torch.nn.functional as F

from chuanma.actions import Action

from .dataset import Arrays, Dataset
from .model import VALUE_SCALE, MahjongNet, ModelConfig, save_checkpoint


def to_device(batch: Arrays, device: torch.device):
    return tuple(torch.from_numpy(a).to(device, non_blocking=True) for a in batch)


def prefetch(batches: Iterator[Arrays], depth: int = 4) -> Iterator[Arrays]:
    """另开一个线程提前取批,取数和训练不互相等。"""
    q: "queue.Queue" = queue.Queue(maxsize=depth)

    def work() -> None:
        for b in batches:
            q.put(b)
        q.put(None)

    threading.Thread(target=work, daemon=True).start()
    while True:
        b = q.get()
        if b is None:
            return
        yield b


def losses(model: MahjongNet, obs, oracle, mask, action, ret, value_weight: float):
    out = model(obs, mask, oracle)
    policy = F.cross_entropy(out.logits, action)
    target = ret / VALUE_SCALE
    value = F.smooth_l1_loss(out.value, target)
    oracle_value = F.smooth_l1_loss(out.oracle_value, target)
    total = policy + value_weight * (value + oracle_value)
    return total, policy, value, oracle_value, out


@torch.no_grad()
def validate(model: MahjongNet, data: Dataset, device: torch.device, batch_size: int = 4096) -> Dict[str, float]:
    model.eval()
    hit: Dict[str, int] = defaultdict(int)
    seen: Dict[str, int] = defaultdict(int)
    sums = defaultdict(float)
    n = 0
    for batch in data.batches(batch_size, shuffle=False):
        obs, oracle, mask, action, ret = to_device(batch, device)
        with torch.autocast(device.type, enabled=device.type == "cuda"):
            _, policy, value, oracle_value, out = losses(model, obs, oracle, mask, action, ret, 0.0)
        k = len(action)
        n += k
        sums["policy_loss"] += policy.item() * k
        sums["value_loss"] += value.item() * k
        sums["oracle_value_loss"] += oracle_value.item() * k
        correct = (out.logits.argmax(1) == action).cpu().numpy()
        for a, ok in zip(batch.action.tolist(), correct.tolist()):
            kind = Action.from_id(a).type.name
            seen[kind] += 1
            hit[kind] += ok
    model.train()
    result = {k: v / n for k, v in sums.items()}
    result["accuracy"] = sum(hit.values()) / n
    for kind in seen:
        result[f"acc_{kind}"] = hit[kind] / seen[kind]
    return result


def train(
    data_dirs: List[str],
    val_dirs: List[str],
    out_dir: str,
    epochs: float = 4.0,
    batch_size: int = 1024,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    value_weight: float = 0.5,
    config: ModelConfig = ModelConfig(),
    device: Optional[str] = None,
    max_samples: Optional[int] = None,
    eval_every: int = 2000,
    seed: int = 0,
    log=print,
) -> Dict[str, float]:
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    torch.manual_seed(seed)
    t0 = time.perf_counter()
    data = Dataset(data_dirs, max_samples)
    val = Dataset(val_dirs, max_samples)
    log(f"训练集 {len(data):,} 个样本,验证集 {len(val):,} 个,读入用时 {time.perf_counter() - t0:.0f} 秒")

    model = MahjongNet(config).to(dev)
    log(f"网络 {config.blocks} 个残差块 × {config.channels} 通道,{model.num_parameters():,} 个参数,设备 {dev}")
    steps_per_epoch = len(data) // batch_size
    total_steps = max(1, int(steps_per_epoch * epochs))
    warmup = min(500, total_steps // 10)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt,
        lambda s: (s + 1) / warmup if s < warmup else 0.5 * (1 + math.cos(math.pi * (s - warmup) / max(1, total_steps - warmup))),
    )
    use_amp = dev.type == "cuda"
    scaler = torch.amp.GradScaler(enabled=use_amp)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log_file = (out / "log.csv").open("w", newline="", encoding="utf-8")
    writer: Optional[csv.DictWriter] = None

    step = 0
    best = -1.0
    last: Dict[str, float] = {}
    running = defaultdict(float)
    count = 0
    start = time.perf_counter()
    model.train()
    epoch = 0
    while step < total_steps:
        for batch in prefetch(data.batches(batch_size, seed=seed + epoch, drop_last=True)):
            obs, oracle, mask, action, ret = to_device(batch, dev)
            with torch.autocast(dev.type, enabled=use_amp):
                total, policy, value, oracle_value, _ = losses(model, obs, oracle, mask, action, ret, value_weight)
            opt.zero_grad(set_to_none=True)
            scaler.scale(total).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            step += 1
            running["policy"] += policy.item()
            running["value"] += value.item()
            running["oracle"] += oracle_value.item()
            count += 1

            if step % eval_every == 0 or step == total_steps:
                last = validate(model, val, dev)
                elapsed = time.perf_counter() - start
                row = {
                    "step": step,
                    "epoch": round(step / steps_per_epoch, 3),
                    "seconds": round(elapsed, 1),
                    "train_policy_loss": round(running["policy"] / count, 4),
                    "train_value_loss": round(running["value"] / count, 4),
                    "train_oracle_value_loss": round(running["oracle"] / count, 4),
                    **{k: round(v, 4) for k, v in sorted(last.items())},
                }
                running.clear()
                count = 0
                if writer is None:
                    writer = csv.DictWriter(log_file, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
                log_file.flush()
                log(
                    f"第 {step}/{total_steps} 步({row['epoch']} 轮,{elapsed:.0f} 秒,"
                    f"{step * batch_size / elapsed:,.0f} 样本/秒): 训练损失 {row['train_policy_loss']},"
                    f"验证集同步率 {last['accuracy']:.4f},价值损失 {last['value_loss']:.4f} / 看全场 {last['oracle_value_loss']:.4f}"
                )
                extra = dict(step=step, metrics=last, stage="bc")
                save_checkpoint(out / "latest.pt", model, **extra)
                if last["accuracy"] > best:
                    best = last["accuracy"]
                    save_checkpoint(out / "best.pt", model, **extra)
            if step >= total_steps:
                break
        epoch += 1
    log_file.close()
    return last


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ai.train_bc", description="模仿学习")
    parser.add_argument("--data", nargs="+", required=True, help="训练数据目录,可以给多个")
    parser.add_argument("--val", nargs="+", required=True, help="验证数据目录")
    parser.add_argument("--out", default="checkpoints/bc")
    parser.add_argument("--epochs", type=float, default=4.0)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--value-weight", type=float, default=0.5)
    parser.add_argument("--channels", type=int, default=128)
    parser.add_argument("--blocks", type=int, default=10)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--eval-every", type=int, default=2000)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    last = train(
        args.data,
        args.val,
        args.out,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        value_weight=args.value_weight,
        config=ModelConfig(channels=args.channels, blocks=args.blocks),
        device=args.device,
        max_samples=args.max_samples,
        eval_every=args.eval_every,
    )
    print("各类动作的同步率:")
    for k, v in sorted(last.items()):
        if k.startswith("acc_"):
            print(f"  {k[4:]:<12} {v:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

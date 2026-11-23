"""生成报牌的人声: 四个座位各用一个音色,27 种数牌、7 种字牌,加上"碰、杠、胡、自摸、吃、立直、荣和"。

川麻用前 27 种牌和"碰、杠、胡、自摸";日麻另外用字牌和"吃、立直、荣和"(牌的编号两边一致: 0-26 万筒条,
27-33 东南西北白发中)。只补新加的句子用 --missing。

这个脚本不在项目自己的环境里跑。它用的是另一个项目(眠屿)在本机部署的 Qwen3-TTS
和那边已经定好的四个音色,所以要用那边的 Python 来运行:

    D:\\sleep\\tts\\.venv\\Scripts\\python tools\\make_voice.py

做法: 用每个音色"平常说话"的样本做参考音频克隆;每句话生成几遍,去掉首尾的静音,
挑时长居中的那一遍(太长太短的多半是读错了或者拖了尾音);统一音量后用 ffmpeg 压成 mp3,
放到 frontend/public/voice/<音色>/<键>.mp3,并写出 manifest.json。
显卡要有 5 GB 左右的空闲显存;没有的话加 --cpu(慢很多)。

挑选只看时长,不能代替人听一遍。听着不对的句子可以单独重做:
    ... tools\\make_voice.py --only qingnian:t3,yujie:pong --seed 7
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

ROOT = Path(__file__).resolve().parent.parent

# 东、南、西、北四个座位依次用哪个音色: (文件夹名, 眠屿那边的音色名)
VOICES = [("qingnian", "青年音"), ("yujie", "御姐音"), ("jiaoshou", "老教授音"), ("tianmei", "甜妹音")]
NUMBERS = "一二三四五六七八九"
SUITS = "万筒条"  # 和引擎里牌的编号顺序一致: 0-8 万,9-17 筒,18-26 条
PHRASES = {f"t{s * 9 + r}": f"{NUMBERS[r]}{SUITS[s]}。" for s in range(3) for r in range(9)}
PHRASES.update({"pong": "碰!", "gang": "杠!", "hu": "胡了!", "zimo": "自摸!"})
# 日麻: 字牌和日麻特有的喊话
PHRASES.update({f"t{27 + i}": f"{name}。" for i, name in enumerate("东南西北白发中")})
PHRASES.update({"chi": "吃!", "riichi": "立直!", "ron": "荣和!"})

MIN_SECONDS, MAX_SECONDS = 0.22, 1.6
TARGET_RMS = 0.11


def trim(wav: np.ndarray, sr: int) -> np.ndarray:
    """去掉首尾的静音,留一点点头尾,再加很短的淡入淡出免得有"咔"的一声。"""
    cut, (start, end) = librosa.effects.trim(wav, top_db=32, frame_length=1024, hop_length=128)
    pad = int(sr * 0.03)
    out = wav[max(0, start - pad) : min(len(wav), end + pad)].astype(np.float32).copy()
    fade = min(int(sr * 0.012), len(out) // 4)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        out[:fade] *= ramp
        out[-fade:] *= ramp[::-1]
    return out


def level(wav: np.ndarray) -> np.ndarray:
    """统一音量: 按均方根对齐,峰值不超过 0.95。"""
    rms = float(np.sqrt(np.mean(wav**2))) or 1e-6
    out = wav * (TARGET_RMS / rms)
    peak = float(np.max(np.abs(out))) or 1e-6
    return out * min(1.0, 0.95 / peak)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices-dir", default="D:/sleep/sleep-mvp/content-work/lectures/voices")
    ap.add_argument("--models-dir", default="D:/sleep/tts/models")
    ap.add_argument("--out", default=str(ROOT / "frontend" / "public" / "voice"))
    ap.add_argument("--raw", default=str(ROOT / "data" / "voice_raw"), help="保留没压缩的 wav 和全部候选的时长")
    ap.add_argument("--takes", type=int, default=3, help="每句话生成几遍")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default="", help="只重做这些,例如 qingnian:t3,yujie:pong")
    ap.add_argument("--missing", action="store_true", help="只生成还没有 mp3 的句子")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()

    ffmpeg = shutil.which("ffmpeg") or "D:/ffmpeg/bin/ffmpeg.exe"
    out_dir, raw_dir = Path(args.out), Path(args.raw)
    only = {tuple(x.split(":")) for x in args.only.split(",") if x}
    kw = (
        dict(device_map="cpu", dtype=torch.float32)
        if args.cpu
        else dict(device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")
    )
    model = Qwen3TTSModel.from_pretrained(str(Path(args.models_dir) / "Qwen3-TTS-12Hz-1.7B-Base"), **kw)
    report = {}
    for vid, vname in VOICES:
        keys = [k for k in PHRASES if not only or (vid, k) in only]
        if args.missing:
            keys = [k for k in keys if not (out_dir / vid / f"{k}.mp3").is_file()]
        if not keys:
            continue
        vdir = Path(args.voices_dir) / vname
        moods = json.loads((vdir / "moods" / "moods.json").read_text(encoding="utf-8"))
        # 用"平常说话"的那段样本做参考: 比睡前讲故事的本音利落,适合报牌
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(vdir / "moods" / moods["plain"]["file"]), ref_text=moods["plain"]["text"]
        )
        takes = {k: [] for k in keys}
        for take in range(args.takes):
            torch.manual_seed(1000 * (args.seed + 1) + take)
            start = time.time()
            wavs, sr = model.generate_voice_clone(
                text=[PHRASES[k] for k in keys],
                language=["Chinese"] * len(keys),
                voice_clone_prompt=prompt * len(keys) if isinstance(prompt, list) and len(prompt) == 1 else prompt,
                max_new_tokens=48,
            )
            for k, w in zip(keys, wavs):
                takes[k].append(trim(np.asarray(w, dtype=np.float32), sr))
            print(f"{vname} 第 {take + 1} 遍: {len(keys)} 句,用时 {time.time() - start:.0f} 秒", flush=True)

        (out_dir / vid).mkdir(parents=True, exist_ok=True)
        (raw_dir / vid).mkdir(parents=True, exist_ok=True)
        for k in keys:
            lengths = [len(w) / sr for w in takes[k]]
            ok = [i for i, d in enumerate(lengths) if MIN_SECONDS <= d <= MAX_SECONDS]
            pool = ok or list(range(len(lengths)))
            pick = sorted(pool, key=lambda i: lengths[i])[len(pool) // 2]  # 时长居中的那一遍
            wav = level(takes[k][pick])
            raw = raw_dir / vid / f"{k}.wav"
            sf.write(raw, wav, sr)
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-ac", "1", "-ar", "24000", "-b:a", "48k", str(out_dir / vid / f"{k}.mp3")],
                check=True,
            )
            report[f"{vid}:{k}"] = {
                "text": PHRASES[k],
                "seconds": round(lengths[pick], 2),
                "takes": [round(d, 2) for d in lengths],
                "suspect": not ok,
            }

    manifest = {"voices": [{"id": v, "name": n} for v, n in VOICES], "keys": list(PHRASES)}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    old = {}
    report_path = raw_dir / "report.json"
    if (only or args.missing) and report_path.is_file():
        old = json.loads(report_path.read_text(encoding="utf-8"))
    report_path.write_text(json.dumps({**old, **report}, ensure_ascii=False, indent=1), encoding="utf-8")
    suspect = [k for k, r in report.items() if r["suspect"]]
    print(f"完成 {len(report)} 句。时长不在 {MIN_SECONDS}-{MAX_SECONDS} 秒之间、需要重点听的: {suspect or '没有'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

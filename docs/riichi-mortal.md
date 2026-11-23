# 接入 Mortal

[Mortal](https://github.com/Equim-chan/Mortal) 是公开的日麻 AI 里最强的一个。我们接它有两个用途:

| 用途 | 做法 |
|---|---|
| 外部标尺 | 和我们的模型同桌,用同一个种子打 4 次、轮流坐 4 个座位,看名次分差多少 |
| 老师 | 四家都是 Mortal,记下它每一步的选择和 Q 值,当作模仿学习的数据,替换规则型老师 |

## 1. 用的是哪个 Mortal

| 项 | 内容 |
|---|---|
| 权重 | 社区放出的 [haor/Mortal-S42](https://huggingface.co/haor/Mortal-S42)(官方不发权重) |
| 网络 | Mortal v4:192 通道 × 40 个残差块,对决式 DQN 头,1084 万参数 |
| 训练数据 | 天凤凤凰桌 + 雀魂的人类牌谱,离线强化学习(CQL),没有在线自我对弈 |
| 许可证 | 权重 Apache-2.0;运行时(libriichi 和 model.py、engine.py)AGPL-3.0 |
| 放在哪 | 本机 `.mortal/`,已加进 `.gitignore`,**不入库、不随项目发布** |

AGPL 的代码只在本机跑评估和生成数据。我们的模型学的是它在对局里的选择,这些选择本身不是 AGPL 代码。

## 2. 安装(Windows,本机已经装好)

| 步骤 | 命令或说明 |
|---|---|
| Rust | 官方 `rustup-init.exe`,再装 GNU 版工具链:`rustup toolchain install stable-x86_64-pc-windows-gnu --profile minimal` |
| C 编译器 | [WinLibs](https://github.com/brechtsanders/winlibs_mingw) 的 MinGW(UCRT,不带 LLVM 那个),解压到 `.mortal/winlibs/` |
| 权重和运行时 | `git clone https://huggingface.co/haor/Mortal-S42 .mortal/s42`(要 git-lfs),对一下 `SHA256SUMS.txt` |
| 改一处 | `runtime/Cargo.toml` 的 workspace 里删掉 `"exe-wrapper"`(这个目录没有放出来) |
| 编译 | 见下面 |
| 自检 | `cd .mortal/s42 && python inference.py --smoke --device cpu`,输出 `"result": "pass"` |

编译要在 PowerShell 里跑。Git Bash 自带的 `/usr/bin/link` 会挡住链接器;VS 2022 没装 C++ 工作负载时也没有 MSVC 的 `link.exe`,所以用 GNU 工具链加 WinLibs:

```powershell
$m = "<项目目录>\.mortal"; $rt = "$m\s42\runtime"
$env:PATH = "$env:USERPROFILE\.cargo\bin;$m\winlibs\mingw64\bin;$env:PATH"
$env:PYO3_PYTHON = (python -c "import sys;print(sys.executable)")
$env:CARGO_TARGET_DIR = "$rt\target-gnu"
cd $rt; cargo +stable-x86_64-pc-windows-gnu build --release -p libriichi
copy "$rt\target-gnu\release\riichi.dll" "$rt\mortal\libriichi.cp311-win_amd64.pyd"
```

编出来的扩展绑定当时的 Python 版本(这里是 3.11)。用项目平时的 Python 就行,torch 2.7 也能用,不需要另建虚拟环境。

## 3. 转换层(`riichi_ai/mjai.py`)

Mortal 只认 mjai 协议:一行一个 JSON 事件,轮到它决定时回一个动作。我们的引擎本来就记事件流,逐条翻译过去就行。

| 本项目 | mjai |
|---|---|
| hand_start | start_kyoku(别家配牌写 "?") |
| draw / discard | tsumo(别家摸的牌写 "?")/ dahai |
| riichi / riichi_accepted | reach / reach_accepted |
| chi / pon / 大明杠 / 暗杠 | chi / pon / daiminkan / ankan |
| kan_declared(加杠宣言) | kakan(之后的"加杠完成"不再发) |
| hand_end | 每个和牌的人一条 hora,或 ryukyoku;再加 end_kyoku |

| 细节 | 处理 |
|---|---|
| 每走一步 | 所有 Mortal 座位都同步一次新事件(加杠宣言要在当步翻译,那时碰的三张还在) |
| 回应的缓存 | 每个事件喂进去,Mortal 可能回一个动作;轮到它时用最近一次回应 |
| 明杠的新宝牌 | 下一张弃牌之后才翻。对 dahai 的回应(比如碰)不能被紧跟着的 dora 事件冲掉。最早的 4 次对不上全是这个原因,已修 |
| 回应 → 动作 | 吃碰按 consumed 推出形状和是否用赤 5;和牌按阶段分成自摸或荣和;过就是 PASS |
| 对不上时 | 回应在我们引擎里不合法:能过就过,否则规则型代打,计一次"对不上" |
| Q 值 | 回应里的 `meta.q_values` 按 `mask_bits` 摊回 46 个动作,再换算到我们的 119 个动作 |

## 4. 用法(`riichi_ai/mortal.py`)

```bash
python -m riichi_ai.mortal smoke                    # Mortal 和三个规则型打一场
python -m riichi_ai.mortal smoke --all              # 四家都是 Mortal
python -m riichi_ai.mortal eval --other shanten --deals 40 --workers 6           # Mortal 对 3 个规则型
python -m riichi_ai.mortal eval --other checkpoints/riichi_ppo/best.pt --ours --deals 40 --workers 6   # 我们的模型对 3 个 Mortal
python -m riichi_ai.mortal generate --games 2000 --workers 12 --out data/rmortal/a   # 蒸馏数据
```

生成的数据和 `riichi_ai.generate` 格式一样,`train_bc` 可以直接读;另多一列 `q`(Mortal 的 Q 值,不合法的动作是 −inf),留给之后的软标签蒸馏。种子从 3000 万起,和训练、评估、段位梯都不重叠。

## 5. 结果

2026-11-23,40 个种子 × 4 个座位 = 160 场半庄(种子从 3000 万起),Mortal 在 CPU 上跑:

| 甲 对 3 个乙 | 平均名次分 | 95% 区间 | 平均顺位 | 和了率 | 放铳率 |
|---|---|---|---|---|---|
| Mortal 对 3 个规则型 | **+14.72** | [+10.94, +18.50] | 2.038 | 24.6% | 8.7% |
| 自我对弈第 180 轮 对 3 个 Mortal | −11.36 | [−17.74, −4.98] | 2.862 | 19.2% | 18.9% |
| 规则型 对 3 个 Mortal | −14.85 | [−19.45, −10.26] | 2.950 | 19.5% | 20.8% |

| 看法 | 依据 |
|---|---|
| 转换层可靠 | 三组里 Mortal 一共决定 16.6 万次,0 次对不上、0 次出错 |
| 差距很大 | Mortal 对规则型 +14.7;我们的模型对规则型(段位梯)只有 +3.7 |
| 主要差在防守 | 同样和三个 Mortal 同桌,我们放铳 18.9%;Mortal 和三个规则型同桌只放铳 8.7% |
| 我们比规则型好一点 | 对 Mortal 时 −11.4 对 −14.9,方向对,但两个区间有重叠,160 场半庄分不清 |

只有 160 场半庄,区间有 ±5 左右,只能看大致的差距。

试生成的蒸馏数据(四家 Mortal,24 场半庄):1.6 万个决策点,6 个进程 99 秒。Q 值最大的动作和 Mortal 实际选的 99.9% 一致;第一和第二选择的 Q 值差中位数约 2,所以软标签的温度先取 1。

## 6. 学 Mortal(2026-11-23)

整条流程在 `.mortal/learn_mortal.sh`(本机,不入库),一步失败就停:

```bash
python -m riichi_ai.mortal generate --games 200  --workers 10 --seed 32000000 --out data/rmortal/val
python -m riichi_ai.mortal generate --games 4000 --workers 10 --seed 31000000 --out data/rmortal/train
python -m riichi_ai.train_bc --data data/rmortal/train --val data/rmortal/val --out checkpoints/riichi_mortal_bc   --init checkpoints/riichi_ppo/best.pt --soft-weight 1.0 --soft-temp 1.0 --lr 5e-4 --epochs 3
python -m riichi_ai.export --checkpoint checkpoints/riichi_mortal_bc/best.pt --out models/riichi.onnx
```

| 项 | 内容 |
|---|---|
| 数据 | 四家 Mortal,训练集 4000 场半庄(238 万个决策点,10 个进程 88 分钟),验证集 200 场(11.9 万个,6 分钟);Mortal 一共决定 264 万次,0 次对不上 |
| 训练 | 从自我对弈第 180 轮出发;损失 = 硬标签 + 软标签(softmax(Q / 1) 的交叉熵,权重 1);学习率 5e-4,3 轮,RTX 4060 Ti 5.5 分钟 |
| 验证集同步率 | 88.0%:出牌 86.1%、碰 87.6%、吃 62.6%、立直 81.0%、过 98.1%、和牌 100% |
| 入座 | 导出成 `models/riichi.onnx`,替换了只自我对弈的那一版 |

和只自我对弈的第 180 轮比(同一批种子、同样场数):

| 对手 | 只自我对弈 | 学过 Mortal | 看法 |
|---|---|---|---|
| 3 个规则型(种子 2000 万起,1200 场半庄) | +3.68 [+1.88, +5.47] | **+8.43 [+6.42, +10.44]** | 区间不重叠,确实变强 |
| 放铳率(对规则型) | 12–13%(定期评估) | **9.7%** | 主要的提升在防守 |
| 3 个 Mortal(种子 3000 万起,160 场半庄) | −11.36 [−17.74, −4.98] | −8.84 [−13.49, −4.20] | 方向对,区间重叠,还说不准 |
| 放铳率(对 Mortal) | 18.9% | 15.5% | — |

| 没做的 / 没核实的 | 说明 |
|---|---|
| 吃 | 同步率只有 62.6%,最弱的一类 |
| 大明杠 | 同步率 0,应该是样本太少,没核实 |

段位梯加上这一版(1200 场半庄,种子 2000 万起):对只自我对弈的版本 +3.80 [+1.96, +5.64],反过来 −4.22 [−6.31, −2.13],两个方向都显著更强。

## 7. 学过 Mortal 之后再自我对弈(2026-11-23)

```bash
python -m riichi_ai.train_ppo --init checkpoints/riichi_mortal_bc/best.pt --out checkpoints/riichi_ppo2 --minutes 180 --workers 10
```

| 项 | 内容 |
|---|---|
| 训练量 | 243 轮,11.9 万场半庄,2.9 小时;对手池 0 号位是学过 Mortal 的版本 |
| 定期评估 | 对 3 个规则型(种子 1000 万起,600 场)在 +8.9 到 +13.2 之间来回;最高是第 220 轮 +13.17,是 12 次里挑的最高分,偏高 |

用段位梯的种子重测第 220 轮:

| 对手 | 学过 Mortal(入座中) | 再自我对弈第 220 轮 | 看法 |
|---|---|---|---|
| 3 个规则型(1200 场半庄) | +8.43 [+6.42, +10.44] | +11.15 [+9.18, +13.11] | 高 2.7,区间有重叠 |
| 两版直接同桌(1200 场半庄) | — | −0.41 [−2.24, +1.43] | 分不出高下 |
| 3 个 Mortal(160 场半庄) | −8.84 [−13.49, −4.20] | −7.38 [−13.52, −1.23] | 场数太少,分不清 |
| 和了率 / 放铳率(对规则型) | 23.3% / 9.7% | 25.3% / 11.5% | 进攻变强,防守变差 |

结论:再自我对弈学到的主要是更会赢规则型,对学过 Mortal 的版本没有显著提升,所以入座模型没换。

## 8. 下一步

| 顺序 | 做什么 |
|---|---|
| 1 | 自我对弈的评估对手换成学过 Mortal 的版本(或 Mortal 本身),挑 best.pt 不再只看规则型 |
| 2 | 自我对弈时加一项"别离老师太远"的约束(对学过 Mortal 版本的 KL),保住防守 |
| 可选 | 把多桌的 Mortal 推理合成一批放到显卡上,生成会快很多,能生成更多数据 |

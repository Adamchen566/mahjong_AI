# Mahjong AI — 四川麻将(血战到底)

一个能打的四川麻将软件,加上一个自己训练出来的麻将 AI。

| 目标 | 内容 | 状态 |
|---|---|---|
| 1. 可使用的麻将软件 | 浏览器里 1 人对 3 个电脑,完整打一局并结算 | 未开始(阶段 2) |
| 2. 训练 AI | 规则型 AI 打底,再用自我对弈强化学习 | 未开始(阶段 4) |
| 3. AI 加入对局 | 训练出的模型作为不同难度的对手坐进牌局 | 未开始(阶段 5) |
| 地基:规则引擎 | 无界面、可复现的川麻状态机,三个目标共用 | **已完成(阶段 0、1)** |

联机对战不在当前范围内。完整计划见 [docs/roadmap.md](docs/roadmap.md)。

## 现在能做什么

规则引擎 `chuanma` 已经可用,纯 Python 标准库,没有第三方依赖。

```bash
python -m chuanma play --seed 1
```

四个内置的简单策略打一局,逐步打印摸牌、出牌、碰杠、胡牌和每一笔分数。

```bash
python -m chuanma simulate -n 2000
```

批量对局,输出速度、胡牌率、平均得分。

```bash
python -m pytest
```

跑全部测试(需要 `pip install pytest`)。

在代码里使用:

```python
from chuanma import Game, SimpleAgent

game = Game(seed=1)
agents = [SimpleAgent(s) for s in range(4)]
while not game.is_over:
    seat = game.current                       # 轮到谁做决定
    obs = game.observation(seat)              # 这个座位能看到的信息
    action = agents[seat].act(obs, game.legal_actions())
    game.step(action)
print(game.scores, game.wins)
```

## 引擎支持的规则

| 类别 | 内容 |
|---|---|
| 流程 | 换三张、定缺、血战到底(胡牌者离场,打到三家胡或牌墙摸完) |
| 行牌 | 碰、直杠、暗杠、加杠、自摸、点炮、一炮多响、抢杠胡 |
| 番型 | 平胡、对对胡、七对、龙七对、清一色、带幺九、将对、金钩钓、根、门清、中张、天胡、地胡 |
| 场况 | 杠上花、杠上炮、海底捞月、海底炮、自摸加底/加番 |
| 结算 | 刮风下雨(杠分)、查花猪、查大叫、退税、封顶 |

各地规则有出入,有分歧的地方都是配置项。确切的规则、番表和没实现的部分见 [docs/rules.md](docs/rules.md)。

## 目录

```
.
├── chuanma/          规则引擎(阶段 1)
│   ├── tiles.py        牌的编码与解析
│   ├── config.py       规则配置
│   ├── actions.py      动作与 0..114 的固定编号
│   ├── hand.py         判胡、拆牌、听牌
│   ├── fan.py          番型与番数
│   ├── game.py         状态机: 流程、合法动作、计分、各座位视图
│   ├── record.py       牌谱保存与复盘
│   ├── agents.py       策略接口 + RandomAgent / SimpleAgent
│   ├── runner.py       对局与批量统计
│   └── __main__.py     命令行
├── tests/            测试(规则逐条验证 + 随机对局不变量)
├── docs/             项目文档
├── frontend/         React + Vite 脚手架,阶段 2 在此基础上做牌桌界面
└── legacy/           2025 年 5 月的旧版代码,只保留作参考
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/roadmap.md](docs/roadmap.md) | 分阶段计划、每阶段的交付物和验收标准、当前进度 |
| [docs/rules.md](docs/rules.md) | 引擎实现的确切规则、番表、配置项、未实现的规则 |
| [docs/architecture.md](docs/architecture.md) | 整体架构、引擎接口、视图字段、动作编号、事件、牌谱格式 |
| [docs/ai-training.md](docs/ai-training.md) | AI 训练方案、硬件条件、评估方法 |

## 环境

| 项 | 要求 |
|---|---|
| Python | 3.10 及以上(开发机为 3.11.9) |
| 引擎依赖 | 无 |
| 测试 | pytest |
| 之后的阶段 | 阶段 2 需要 FastAPI、Node.js;阶段 4 需要带 CUDA 的 PyTorch,见 [docs/ai-training.md](docs/ai-training.md) |

## 关于 legacy/

`legacy/` 是重构前的代码:终端版和 tkinter 版川麻、南京麻将骨架、摄像头识牌脚本、联网雏形。新代码不依赖它。说明见 [legacy/README.md](legacy/README.md)。

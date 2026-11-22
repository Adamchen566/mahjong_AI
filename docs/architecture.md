# 架构与引擎接口

## 1. 整体结构

三个目标共用一个规则引擎。引擎不知道界面、网络和神经网络的存在,其他部分都通过同一个小接口使用它。

```
             ┌─────────────┐   ┌──────────────┐   ┌──────────────┐
             │ 牌桌界面     │   │ 训练环境      │   │ 同牌对比评估  │
             │ server/前端  │   │ (未开始)      │   │ ai/evaluate  │
             └──────┬──────┘   └──────┬───────┘   └──────┬───────┘
                    │                 │                  │
             ┌──────▼─────────────────▼──────────────────▼───────┐
             │ 策略接口  Agent.act(observation, legal) -> Action  │
             │ 人 / SimpleAgent / RuleAgent / 神经网络(未开始)     │
             └──────────────────────┬────────────────────────────┘
                                    │
             ┌──────────────────────▼────────────────────────────┐
             │ 规则引擎 chuanma.Game                              │
             │ legal_actions()  step()  observation()  events    │
             └───────────────────────────────────────────────────┘
```

| 设计原则 | 做法 | 原因 |
|---|---|---|
| 引擎无副作用 | 不打印、不读输入、不访问文件和网络 | 同一份代码要每秒跑上千局训练,也要驱动界面 |
| 完全可复现 | 随机性只来自种子;种子 + 动作序列 = 同一局 | 复盘、查 bug、用同一副牌对比不同 AI |
| 一次只有一个决策者 | "同时决定"的环节拆成逐个询问 | 训练框架和界面都只需处理"轮到谁、能做什么" |
| 信息隔离在引擎里做 | `observation(seat)` 只给该座位能看到的信息 | AI 不可能偷看;界面拿到什么就能显示什么 |
| 计分只有一个出口 | 所有分数变动都记成一笔 `Transfer` | 四家总分恒为 0;退税只需反向重放 |

## 2. 模块

| 模块 | 职责 | 依赖 |
|---|---|---|
| `tiles.py` | 牌的整数编码、字符串解析、计数转换 | — |
| `config.py` | `RuleConfig`,所有规则开关 | — |
| `actions.py` | `Action` 及其 0..114 的固定编号 | tiles |
| `hand.py` | 判胡、列出拆法、求听牌 | tiles |
| `shanten.py` | 向听数、有效进张 | tiles |
| `fan.py` | 番型、番数、查大叫用的最大番 | hand, config |
| `game.py` | `Game` 状态机:流程、合法动作、计分、视图、事件 | 以上全部 |
| `record.py` | 牌谱 `GameRecord` 与 `replay` | game |
| `agents.py` | `Agent` 接口、`RandomAgent`、`SimpleAgent` | actions, tiles |
| `runner.py` | `play_game`、`simulate` | game, agents |
| `__main__.py` | 命令行 | 以上全部 |

## 3. 数据表示

| 概念 | 表示 |
|---|---|
| 一种牌 | 整数 0..26,`花色 × 9 + (点数 − 1)`;花色 0 万、1 筒、2 条 |
| 一手牌 | 长度 27 的计数列表,`counts[牌] = 张数` |
| 文本写法 | `"123m456p77s"`(m 万、p 筒、s 条),用 `parse_tiles` / `tiles_str` 转换 |
| 副露 | `Meld(type, tile, from_seat)`,type 为 `PONG` / `MING_GANG` / `AN_GANG` / `JIA_GANG` |
| 座位 | 0..3,行牌顺序为加 1 |

## 4. Game 接口

### 4.1 创建

```python
Game(config=None, seed=None, dealer=0, wall=None, exchange_direction=None, record_events=True)
```

| 参数 | 含义 |
|---|---|
| `config` | `RuleConfig`,默认规则见 [rules.md](rules.md) |
| `seed` | 随机种子,决定洗牌和换牌方向 |
| `dealer` | 庄家座位 |
| `wall` | 指定 108 张牌墙,给了就不洗牌(测试、复盘用)。前 52 张按座位 0–3 每人 13 张发出,第 53 张给庄家,之后依次被摸走 |
| `exchange_direction` | 换三张方向:1 给下家、2 给对家、3 给上家;不给则由种子决定 |
| `record_events` | 是否记录事件流。训练时关掉省时间 |

### 4.2 推进

| 成员 | 含义 |
|---|---|
| `game.is_over` | 是否结束 |
| `game.phase` | 当前阶段,见下表 |
| `game.current` | 轮到哪个座位做决定;结束后为 −1 |
| `game.legal_actions()` | 当前决策者的全部合法动作(`Action` 列表) |
| `game.legal_action_ids()` | 同上,整数编号 |
| `game.step(action)` | 执行一个动作,接受 `Action` 或整数编号。非法动作抛 `IllegalAction`,状态不变 |
| `game.observation(seat)` | 某座位的视图,见 4.4 |
| `game.events` / `game.events_for(seat)` | 事件流,见 4.6 |
| `game.scores` | 四家当前得分,总和恒为 0 |
| `game.wins` | 已发生的胡牌记录 `WinRecord` |
| `game.transfers` | 每一笔分数流转 `Transfer` |
| `game.result()` | 结束后的完整结算 |
| `game.history` | 已执行的动作编号序列 |

### 4.3 阶段

| `Phase` | 谁在决定 | 可选动作 |
|---|---|---|
| `EXCHANGE` | 从庄家起每人依次选 3 张 | `EXCHANGE`(一次选一张,后两张必须与第一张同花色) |
| `CHOOSE_VOID` | 从庄家起每人依次定缺 | `CHOOSE_VOID` |
| `TURN` | 轮到出牌的人 | `DISCARD`、`AN_GANG`、`JIA_GANG`、`HU` |
| `RESPONSE` | 能对刚打出的牌做点什么的人,按座位顺序 | `HU`、`MING_GANG`、`PONG`、`PASS` |
| `ROB_KONG` | 能抢杠的人,按座位顺序 | `HU`、`PASS` |
| `END` | 无 | 无 |

`RESPONSE` 阶段只询问确实有事可做的人;没人能响应时直接进入下一个人的 `TURN`。所有人答完后统一裁决:有人胡则全部胡牌成立,否则杠或碰成立,否则下家摸牌。

### 4.4 视图字段

`game.observation(seat)` 返回一个字典:

| 字段 | 内容 | 是否隐藏信息 |
|---|---|---|
| `seat`、`dealer`、`phase`、`current` | 基本状态 | — |
| `wall_remaining` | 牌墙剩余张数 | — |
| `hand` | 自己的手牌(排好序的牌编号列表) | 只有自己的 |
| `drawn` | 自己这回合刚摸的牌 | 只在自己的回合有值 |
| `hand_sizes` | 四家手牌张数 | — |
| `melds` | 四家的副露,每项 `{type, tile, from_seat}` | 别人暗杠的 `tile` 为 `None` |
| `discards` | 四家的弃牌区(被碰杠走的牌不在其中) | — |
| `void` | 四家的缺门 | 全部定完之前只能看到自己的 |
| `won`、`wins` | 谁已胡牌,以及每次胡牌的牌、番型、分数 | — |
| `scores` | 四家当前得分 | — |
| `pending_discard` | 正在等待响应的那张牌 `{seat, tile}`;抢杠时多一个 `rob_kong: true` | — |
| `after_gang` | 自己回合时:这张牌是杠后补的;响应弃牌时:这张弃牌是杠后打出的 | — |
| `exchange` | `given` 自己换出的牌,`received` 收到的牌,`direction` 方向 | 只有自己的 |
| `legal_actions` | 自己现在的合法动作编号 | 没轮到时为空 |
| `hands`、`end_reason` | 四家手牌、结束原因 | 只在牌局结束后出现 |

### 4.5 动作编号

固定不变,神经网络的输出层和牌谱都用它。

| 编号 | 动作 | 参数 |
|---|---|---|
| 0–26 | `DISCARD` 出牌 | 牌 |
| 27–53 | `AN_GANG` 暗杠 | 牌 |
| 54–80 | `JIA_GANG` 加杠 | 牌 |
| 81 | `PONG` 碰 | — |
| 82 | `MING_GANG` 直杠 | — |
| 83 | `HU` 胡 | — |
| 84 | `PASS` 过 | — |
| 85–87 | `CHOOSE_VOID` 定缺 | 花色 |
| 88–114 | `EXCHANGE` 换三张选牌 | 牌 |

共 115 个(`NUM_ACTIONS`)。`Action.id` 与 `Action.from_id()` 互相转换。

### 4.6 事件

界面按事件播放动画。`events_for(seat)` 在牌局结束前会隐去别人摸到的牌。

| `type` | 字段 |
|---|---|
| `deal` | `dealer` |
| `exchange` | `direction` |
| `void` | `voids` |
| `draw` | `seat`、`tile`、`after_gang` |
| `discard` | `seat`、`tile` |
| `pong` | `seat`、`tile`、`from_seat` |
| `gang_declared` | `seat`、`tile`(加杠后等待抢杠) |
| `gang` | `seat`、`tile`、`kind`、`from_seat` |
| `hu` | `seat`、`tile`、`zimo`、`from_seat`、`fan`、`points`、`names` |
| `transfer` | `kind`、`payer`、`payee`、`amount`、`note` |
| `end` | `reason`(`three_won` / `wall_exhausted`)、`scores` |

## 5. 策略接口

```python
class Agent(Protocol):
    def act(self, obs: dict, legal: list[Action]) -> Action: ...
```

策略只拿到自己座位的视图和合法动作,返回其中之一。

| 内置策略 | 行为 | 用途 |
|---|---|---|
| `RandomAgent` | 随机选 | 压力测试 |
| `SimpleAgent` | 能胡就胡、能杠碰就杠碰,丢最孤立的牌 | 陪练、测试、阶段 2 的临时电脑对手 |

## 6. 牌谱

```json
{
  "version": 1,
  "config": { "base_score": 1, "max_fan": 5, "...": "..." },
  "seed": 42,
  "dealer": 0,
  "exchange_direction": 2,
  "wall": null,
  "actions": [93, 94, 95, "..."],
  "scores": [3, -5, 4, -2],
  "meta": {}
}
```

| 用法 | 代码 |
|---|---|
| 保存 | `GameRecord.from_game(game).save(path)` |
| 读取并重放 | `replay(GameRecord.load(path))` |
| 只放前 n 步 | `replay(record, upto=n)` |

有种子时不存牌墙;用自定义牌墙开的局会把牌墙存进去。重放到底时会核对分数,不一致就报错。

## 7. 正确性保证

| 手段 | 内容 |
|---|---|
| 规则用例 | `tests/test_game_flow.py`、`tests/test_fan.py`、`tests/test_hand.py`:每条规则摆一个局面验证合法动作和分数 |
| 随机对局不变量 | `tests/test_invariants.py`:每种牌恒为 4 张、四家总分恒为 0、手牌张数正确、胡牌者手里没有缺门牌、番数不超封顶 |
| 可复现 | 同种子两次对局的动作、分数、事件完全一致 |
| 可复盘 | 牌谱存盘再读回重放,结果一致;篡改分数会被发现 |

## 8. 性能

开发机(Ryzen 7 9800X3D)单核、四个 `SimpleAgent`、每步都构造视图字典:约 650–690 局/秒,平均每局 78 次决策。

| 如果不够快 | 做法 |
|---|---|
| 第一步 | 多进程并行(对局之间互不相关) |
| 第二步 | 训练时不走视图字典,直接从 `Game` 的内部状态编码成张量(已做:`ai/encoding.py`,12 进程随机策略实测 12.5 万个决定/秒) |
| 第三步 | 把判胡和向听数用 Numba 或 Rust 重写 |

## 9. 引擎之上的三层

| 包 | 内容 | 依赖 |
|---|---|---|
| `ai/` | `RuleAgent`(规则型 AI)、`make_agent(name)` 名字到策略的登记表、`evaluate` 同牌对比;训练环境 `encoding`(状态编码)、`env`(并行对局)、`generate`(模仿数据) | chuanma;训练环境另需 numpy |
| `server/` | `Match`(一场牌局)、FastAPI 应用、启动入口 | chuanma, ai |
| `frontend/` | 浏览器界面 | 只通过网络和 server 通信 |

### 9.1 Match

`server/match.py` 的 `Match` 不涉及网络,测试直接用它。

| 成员 | 含义 |
|---|---|
| `Match(opponent, seed, human_seat, config, records_dir)` | 一场牌局:1 人 + 3 个同类型的电脑 |
| `start_game()` | 开下一局。庄家按局轮换,种子 = 整场种子 + 局数 |
| `waiting_for_human` / `bot_to_act` | 现在轮到人还是电脑 |
| `bot_step()` | 让当前的电脑走一步 |
| `human_action(id)` | 人走一步;没轮到或动作非法会抛异常 |
| `snapshot()` | 人这个座位的视图 + 自上次以来的新事件 + 整场信息 |
| `totals` | 四家累计分,每局结束时累加 |

一局结束时自动把牌谱存进 `records_dir`,文件名形如 `20261122-153000_g3.json`。

### 9.2 WebSocket 协议

地址 `/ws`。本机单人使用,服务端同一时间只保留一场牌局;重新连接会接着打。

| 方向 | 消息 | 含义 |
|---|---|---|
| 浏览器 → 服务 | `{"type": "new_match", "opponent": "rule"}` | 开一场,对手为 `rule` 或 `simple` |
| | `{"type": "action", "id": 12}` | 执行一个动作(编号见 4.5) |
| | `{"type": "actions", "ids": [88, 89, 90]}` | 连续执行,换三张一次交三张 |
| | `{"type": "next_game"}` | 开下一局 |
| | `{"type": "quit_match"}` | 结束整场,回到开始页 |
| 服务 → 浏览器 | `{"type": "state", "match", "view", "events"}` | 每走一步推一次 |
| | `{"type": "error", "message"}` | 请求有问题;随后仍会补发一条 state |

`state` 里的 `view` 就是 `Game.observation(人的座位)`,另加:

| 字段 | 内容 |
|---|---|
| `legal` | 轮到人时的合法动作 `[{id, type, tile}]`,否则为空 |
| `transfers` | 牌局结束后才有:每一笔分数 |
| `record` | 牌局结束后才有:这一局牌谱的文件名 |

电脑行动前服务端会停顿(默认 0.7 秒),换三张和定缺阶段不停顿。

### 9.3 HTTP 接口

| 地址 | 返回 |
|---|---|
| `GET /api/opponents` | 可选的对手类型 |
| `GET /api/records` | 牌谱列表(新的在前) |
| `GET /api/records/{name}` | 一份牌谱的每一步(谁做了什么) |
| `GET /api/records/{name}/view/{step}` | 走到第 step 步之后的局面,四家明牌 |
| `GET /` | 构建好的界面(`frontend/dist`);没构建时显示构建方法 |

### 9.4 界面

React 19 + TypeScript + Vite,没有其他运行时依赖。

| 文件 | 职责 |
|---|---|
| `useGame.ts` | 维护 WebSocket 连接(断线自动重连),把事件转成牌局记录和喊话 |
| `App.tsx` | 开始页、牌桌 + 侧栏的总布局 |
| `Table.tsx` | 牌桌:三个对手、弃牌区、中央方位盘、自己的手牌和操作按钮 |
| `Result.tsx` | 结算单 |
| `Replay.tsx` | 牌谱列表和回放 |
| `tiles.ts` | 牌名、图片路径、事件转文字 |
| `sound.ts` | 音效。全部用 Web Audio 现场合成,不带音频文件;开关存在浏览器的 localStorage 里 |
| `types.ts` | 服务端数据的类型定义 |
| `styles.css` | 全部样式 |

座位在屏幕上的位置:自己在下,下家在右,对家在上,上家在左。

**视觉风格**:遵循「琥珀夜色」设计系统,色值和圆角都以 CSS 变量的形式定义在 `styles.css` 开头。

| 规则 | 在牌桌上的体现 |
|---|---|
| 只有深色主题,暖调炭黑做底 | 页面 `#14130F`,牌桌和侧栏 `#1C1A15`,方位盘和对话框 `#25221B` |
| 琥珀黄不超过 10%,一屏只有一个黄色主按钮 | 黄色只用在:当前行动者、主按钮、选中的牌、最后一张弃牌、"庄"标记 |
| 夜空蓝做副色 | 链接、"展开/收起" |
| 卡片用描边不用阴影 | 只有结算对话框和碰杠胡的喊话有阴影 |
| 状态不只靠颜色 | 分数同时带正负号 |
| 字体 | 设计系统指定的字体不联网加载,本机没有时退回系统中文字体 |

**不打扰的原则**:

| 做法 | 原因 |
|---|---|
| 牌局记录默认收起,点"展开"才显示,新的排在最上面 | 不需要自动滚动,也不会带着整个页面移动 |
| 侧栏只用一行显示最新一条动态 | 不展开记录也知道刚发生了什么 |
| 结算单里的"每一笔分"默认收起 | 先看结论,要细节再点开 |
| 各家缺哪门用符号显示在牌桌中央的方位盘里 | 和风位、庄家、余牌数放在一起,一眼看全;符号是花色图形加斜杠,不写字 |
| 声音只在牌局有动静时响,第一次点击之前静音 | 浏览器不允许页面在用户操作之前出声;不想听可以在侧栏关掉 |

开发界面时可以用 `npm run dev`,Vite 会把 `/api` 和 `/ws` 转给 8000 端口上的 Python 服务。

### 9.5 模型入座、提示、复盘分析

| 项 | 做法 |
|---|---|
| 模型文件 | `models/chuanma.onnx`,由 `python -m ai.export` 从训练存档导出。只含策略头和普通价值头,"看全场"的那一路不导出 |
| 推理 | `ai/onnx_agent.py` 用 onnxruntime 单线程在 CPU 上跑,出一手牌约 0.7 毫秒。对局软件不需要 PyTorch |
| 入座 | 登记表里的名字是 `net`。它和其他电脑一样只拿到自己座位的 `observation()` |
| 缺模型时 | 没有模型文件或没装 onnxruntime:`net` 选不了,提示和分析停用,其余功能照常 |
| 提示 | 浏览器发 `{"type": "hint", "on": true}`。之后轮到人时,视图里多一个 `hint`:`value`(模型估计这一局还会得多少分)和 `choices`(概率最高的三个动作,各带 `prob` 和 `text`) |
| 牌局信息 | `match.hint_available`(有没有模型)、`match.hint_on` |
| 对手列表 | `GET /api/opponents` 每项带 `available` 和 `reason` |
| 复盘分析 | `GET /api/records/{name}/analysis`:`steps[i]` 对应牌谱第 i+1 步,有 `seat`、`forced`、`agree`、`best`、`chosen`、`value`;`summary` 是每个座位做了几次选择、几次和模型首选一样。模型看的是当时那个座位的视图,不是摊开的牌 |

## 10. 之后的阶段怎么接上来

| 阶段 | 接入点 |
|---|---|
| 4b 训练环境 ✅ | `ai/encoding.py` 把 `Game` 的内部状态编码成 71 × 27 的数组,`legal_action_ids()` 生成动作掩码;`ai/env.py` 并行开局,每次决定之间 `scores` 的变化作为回报 |
| 4c–4d 训练 | 网络接在 `ParallelEnv` 上:收一批局面,回一批动作。任务见 [phase4-tasks.md](phase4-tasks.md) |
| 5 AI 入座 | 把神经网络包成一个 `Agent`,在 `ai/__init__.py` 的登记表里加一个名字,界面的难度选项就多一档 |

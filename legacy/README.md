# legacy — 重构前的代码

2025 年 5 月写的第一版,保留作参考,新代码(`chuanma/`)不依赖这里的任何东西。

| 文件 | 内容 |
|---|---|
| `game_chuan.py` | 终端版川麻,人 + KoutsuAI + OracleAI |
| `game_chuan_ui.py`、`ui.py`、`agents/human_ui.py` | tkinter 牌桌界面 |
| `game_nanjing.py` | 南京麻将骨架(无花牌、无计分) |
| `core/` | 旧的规则、番型、记牌器 |
| `agents/` | SimpleAI、KoutsuAI、OracleAI、HumanAgent |
| `simulate_stats.py` | 批量对局统计 |
| `vision_SDK.py`、`vision_dom.py` | 摄像头识别手牌(Roboflow / 本地 YOLO) |
| `server.py`、`static/`、`app/` | Flask-SocketIO 联网雏形和调试接口 |
| `tiles/`、`images/` | 牌面与牌桌图片 |

## 运行

旧代码的导入和图片路径都是相对当前目录的,要先进入 `legacy/`:

```bash
cd legacy
```

```bash
python game_chuan.py
```

`vision_SDK.py` 需要先设置环境变量 `ROBOFLOW_API_KEY`。

## 已知问题

旧版没有修,记在这里只为说明为什么重写:

- 规则、打印、交互混在一个循环里,界面版又复制了一份
- 杠后有人点炮的分支引用了未定义的变量,会报错
- 七对/龙七对判断、带根的碰碰胡、被胡玩家扣分有 bug
- `OracleAI` 读取了全场信息但出牌时没有用上

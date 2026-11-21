# 牌桌界面

React 19 + TypeScript + Vite。只通过 `/ws` 和 `/api` 与本地的 Python 服务通信,协议见 [../docs/architecture.md](../docs/architecture.md) 第 9 节。

| 命令 | 作用 |
|---|---|
| `npm install` | 安装依赖(一次) |
| `npm run build` | 构建到 `dist/`,`python -m server` 会直接提供它 |
| `npm run dev` | 开发模式,接口转给 8000 端口上的 Python 服务 |
| `npm run lint` | 代码检查 |

牌面图片在 `public/tiles/`。

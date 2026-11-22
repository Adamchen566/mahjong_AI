import { useEffect, useState } from 'react'
import { TrainingCurve, two } from './Charts'
import type { Ladder as LadderData } from './types'

/** 段位梯: 从最简单的电脑到训练出来的模型,两两同桌对打的成绩,加上训练曲线。 */
export function Ladder({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<LadderData | null>(null)
  useEffect(() => {
    fetch('/api/ladder')
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ available: false, reason: '问不到本地服务' }))
  }, [])

  const players = data?.players ?? []
  const matrix = data?.matrix ?? []
  return (
    <main className="lobby">
      <div className="lobby-card lobby-wide ladder">
        <h1>AI 段位梯</h1>
        {!data && <p className="lobby-status">正在读取</p>}
        {data && !data.available && (
          <p className="lobby-status">
            现在看不了: {data.reason}。在项目目录里运行 <code>python -m ai.ladder</code> 可以生成。
          </p>
        )}
        {data?.available && (
          <>
            <p className="lobby-sub">
              每一格是"这一行的选手和三个这一列的选手同桌"时,平均每局的得分。每一对打 {data.games_per_pair}{' '}
              局: 同一批牌,四个座位各坐一次。正数表示这一行更强。
            </p>
            <div className="ladder-scroll">
              <table className="records ladder-table">
                <thead>
                  <tr>
                    <th scope="col">选手</th>
                    {players.map((p) => (
                      <th key={p.id} scope="col">
                        对 3 个{p.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {players.map((p, i) => (
                    <tr key={p.id}>
                      <th scope="row">
                        {p.label}
                        <small>{p.note}</small>
                      </th>
                      {players.map((q, j) => {
                        const cell = matrix[i]?.[j]
                        if (!cell) return <td key={q.id} className="ladder-self" aria-label="同一个选手,不比" />
                        const sure = cell.lo > 0 ? 'up' : cell.hi < 0 ? 'down' : ''
                        return (
                          <td
                            key={q.id}
                            title={`95% 区间 ${two(cell.lo)} 到 ${two(cell.hi)},胡牌率 ${Math.round(cell.win_rate * 100)}%,点炮率 ${Math.round(cell.deal_in_rate * 100)}%`}
                          >
                            <b className={sure}>{two(cell.mean)}</b>
                            <small>
                              {two(cell.lo)} 到 {two(cell.hi)}
                            </small>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="chart-note">
              小字是 95% 置信区间。区间整个在 0 以上才标成绿色,整个在 0 以下标成红色;跨过 0 的不上色,表示分不出强弱。
            </p>
            {data.curve && data.curve.length > 1 && <TrainingCurve curve={data.curve} />}
            {data.generated_at && <p className="chart-note">数据生成于 {data.generated_at.replace('T', ' ')}。</p>}
          </>
        )}
        <div className="lobby-buttons">
          <button className="btn btn-ghost" onClick={onClose}>
            返回
          </button>
        </div>
      </div>
    </main>
  )
}

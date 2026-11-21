import { useState } from 'react'
import { Tile } from './Table'
import { signed, transferLabel, whoIs, WINDS } from './tiles'
import type { MatchInfo, View } from './types'

interface ResultProps {
  view: View
  match: MatchInfo
  onNext: () => void
  onReplay?: () => void
}

/** 一局结束后的记分单: 谁胡了什么、每一笔分怎么来的、累计多少。 */
export function Result({ view, match, onNext, onReplay }: ResultProps) {
  const me = match.human_seat
  const transfers = view.transfers ?? []
  const mine = view.scores[me]
  const headline = mine > 0 ? `你赢了 ${mine} 分` : mine < 0 ? `你输了 ${-mine} 分` : '你这局不输不赢'
  const [peek, setPeek] = useState(false) // 收起结算单,看四家摊开的牌

  if (peek) {
    return (
      <div className="result-peek">
        <span>{headline}</span>
        <button className="btn" onClick={() => setPeek(false)}>
          回到结算
        </button>
        <button className="btn btn-primary" onClick={onNext}>
          下一局
        </button>
      </div>
    )
  }

  return (
    <div className="result-veil">
      <section className="result" role="dialog" aria-label="本局结算">
        <header>
          <h2>{headline}</h2>
          <p>
            第 {match.game_no} 局,{view.end_reason === 'three_won' ? '三家已胡' : '牌墙摸完,流局结算'}
          </p>
        </header>

        <table className="result-table">
          <thead>
            <tr>
              <th scope="col">座位</th>
              <th scope="col">结果</th>
              <th scope="col">本局</th>
              <th scope="col">累计</th>
            </tr>
          </thead>
          <tbody>
            {[0, 1, 2, 3].map((seat) => {
              const wins = view.wins.filter((w) => w.seat === seat)
              return (
                <tr key={seat} className={seat === me ? 'is-me' : ''}>
                  <th scope="row">
                    {whoIs(seat, me)}
                    <i>{WINDS[seat]}</i>
                  </th>
                  <td>
                    {wins.length === 0 && <span className="muted">没胡</span>}
                    {wins.map((w, i) => (
                      <span key={i} className="result-win">
                        {w.zimo ? '自摸' : `胡${whoIs(w.from_seat!, me)}`}
                        {w.tile != null && <Tile tile={w.tile} size="xs" />}
                        <em>{w.names.join(' ')}</em>
                        <small>{w.fan} 番</small>
                      </span>
                    ))}
                  </td>
                  <td className={view.scores[seat] > 0 ? 'up' : view.scores[seat] < 0 ? 'down' : ''}>
                    {signed(view.scores[seat])}
                  </td>
                  <td>{signed(match.totals[seat])}</td>
                </tr>
              )
            })}
          </tbody>
        </table>

        <details className="result-detail">
          <summary>每一笔分({transfers.length} 笔)</summary>
          <ol>
            {transfers.map((t, i) => (
              <li key={i}>
                <span>
                  {whoIs(t.payer, me)} 付给 {whoIs(t.payee, me)}
                </span>
                <b>{t.amount}</b>
                <span className="muted">
                  {transferLabel(t.kind)}
                  {t.note && t.kind !== 'tui_shui' && t.kind !== 'hua_zhu' ? `,${t.note.split('/').join(' ')}` : ''}
                </span>
              </li>
            ))}
            {transfers.length === 0 && <li className="muted">这一局没有分数进出</li>}
          </ol>
        </details>

        <footer>
          <button className="btn btn-primary btn-big" onClick={onNext}>
            下一局
          </button>
          <button className="btn" onClick={() => setPeek(true)}>
            看四家的牌
          </button>
          {onReplay && (
            <button className="btn btn-ghost" onClick={onReplay}>
              回放这一局
            </button>
          )}
        </footer>
      </section>
    </div>
  )
}

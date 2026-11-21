import { useState } from 'react'
import { Replay } from './Replay'
import { Result } from './Result'
import { setSoundEnabled, soundEnabled } from './sound'
import { Table } from './Table'
import { signed, whoIs, WINDS } from './tiles'
import type { MatchInfo, View } from './types'
import { useGame, type LoggedLine } from './useGame'

export default function App() {
  const game = useGame()
  const [replay, setReplay] = useState<string | 'list' | null>(null) // 牌谱文件名,或牌谱列表

  if (replay) {
    return <Replay initial={replay === 'list' ? null : replay} onClose={() => setReplay(null)} />
  }
  if (!game.ready) {
    return (
      <main className="lobby">
        <p className="lobby-status">正在连接本地服务</p>
      </main>
    )
  }
  if (!game.match || !game.view) {
    return <Lobby onStart={game.newMatch} onRecords={() => setReplay('list')} connected={game.connected} />
  }

  const { match, view } = game
  return (
    <div className="room">
      <div className="felt">
        <Table view={view} callouts={game.callouts} onAct={game.act} onActMany={game.actMany} />
        {view.phase === 'END' && (
          <Result
            view={view}
            match={match}
            onNext={game.nextGame}
            onReplay={view.record ? () => setReplay(view.record!) : undefined}
          />
        )}
      </div>
      <Sidebar
        match={match}
        view={view}
        log={game.log}
        connected={game.connected}
        error={game.error}
        onRecords={() => setReplay('list')}
        onQuit={game.quitMatch}
      />
    </div>
  )
}

// ---------------------------------------------------------------- 开始页

function Lobby({ onStart, onRecords, connected }: { onStart: (opponent: string) => void; onRecords: () => void; connected: boolean }) {
  const [opponent, setOpponent] = useState('rule')
  const options = [
    { id: 'rule', name: '规则型', note: '会算向听和进张,只在有用的时候碰牌' },
    { id: 'simple', name: '简单', note: '能碰就碰、能杠就杠,丢最孤立的牌' },
  ]
  return (
    <main className="lobby">
      <div className="lobby-card">
        <h1>血战到底</h1>
        <p className="lobby-sub">四川麻将,你和三个电脑。换三张,定缺,打到三家胡牌为止。</p>
        <fieldset className="lobby-options">
          <legend>三个对手的水平</legend>
          {options.map((o) => (
            <label key={o.id} className={opponent === o.id ? 'is-on' : ''}>
              <input type="radio" name="opponent" value={o.id} checked={opponent === o.id} onChange={() => setOpponent(o.id)} />
              <b>{o.name}</b>
              <span>{o.note}</span>
            </label>
          ))}
        </fieldset>
        <div className="lobby-buttons">
          <button className="btn btn-primary btn-big" disabled={!connected} onClick={() => onStart(opponent)}>
            开一桌
          </button>
          <button className="btn btn-ghost" onClick={onRecords}>
            看以前的牌谱
          </button>
        </div>
        {!connected && <p className="lobby-status">和本地服务断开了,正在重连</p>}
      </div>
    </main>
  )
}

// ---------------------------------------------------------------- 侧栏

interface SidebarProps {
  match: MatchInfo
  view: View
  log: LoggedLine[]
  connected: boolean
  error: string | null
  onRecords: () => void
  onQuit: () => void
}

function Sidebar({ match, view, log, connected, error, onRecords, onQuit }: SidebarProps) {
  const me = match.human_seat
  const latest = log.length ? log[log.length - 1] : null
  const [soundOn, setSoundOn] = useState(soundEnabled())
  const toggleSound = () => {
    setSoundEnabled(!soundOn)
    setSoundOn(!soundOn)
  }

  // 本局还没结束时,累计分里不含本局
  const live = view.phase !== 'END'
  return (
    <aside className="side">
      <header className="side-head">
        <h2>第 {match.game_no} 局</h2>
        <span>对手: {match.opponent_label}</span>
      </header>

      <table className="scores">
        <thead>
          <tr>
            <th scope="col">座位</th>
            <th scope="col">本局</th>
            <th scope="col">累计</th>
          </tr>
        </thead>
        <tbody>
          {[0, 1, 2, 3].map((seat) => {
            const total = match.totals[seat] + (live ? view.scores[seat] : 0)
            return (
              <tr key={seat} className={seat === me ? 'is-me' : ''}>
                <th scope="row">
                  {whoIs(seat, me)}
                  <i>{WINDS[seat]}</i>
                </th>
                <td className={cls(view.scores[seat])}>{signed(view.scores[seat])}</td>
                <td className={cls(total)}>{signed(total)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className="latest" aria-live="polite">
        <span>刚刚</span>
        {latest ? latest.text : '这一局还没有动静'}
      </div>

      {/* 牌局记录默认收起,点开才显示;新的排在最上面,不会自己滚动,也不会带着页面跑 */}
      <details className="log-box">
        <summary>牌局记录({log.length} 条)</summary>
        <ol className="log">
          {log.length === 0 && <li className="log-empty">这一局的经过会记在这里</li>}
          {[...log].reverse().map((line) => (
            <li key={line.id} className={`log-${line.kind}`}>
              {line.text}
            </li>
          ))}
        </ol>
      </details>
      <div className="side-spacer" />

      {error && <p className="side-error">{error}</p>}
      {!connected && <p className="side-error">和本地服务断开了,正在重连</p>}

      <footer className="side-foot">
        <button className="btn" onClick={onRecords}>
          牌谱
        </button>
        <button className="btn" onClick={toggleSound} aria-pressed={soundOn}>
          声音 {soundOn ? '开' : '关'}
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => {
            if (window.confirm('结束这一场?累计分数会清零。')) onQuit()
          }}
        >
          结束这一场
        </button>
      </footer>
    </aside>
  )
}

const cls = (n: number) => (n > 0 ? 'up' : n < 0 ? 'down' : '')

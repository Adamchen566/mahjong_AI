import { useEffect, useState } from 'react'
import { InsightPanel } from './Insight'
import { Ladder } from './Ladder'
import { Replay, Viewer } from './Replay'
import { Result } from './Result'
import { Table } from './Table'
import { signed, whoIs, WINDS } from './tiles'
import { SoundToggles, useInsightPreference } from './Toggles'
import type { MatchInfo, View } from './types'
import { useGame, type LoggedLine } from './useGame'

interface Opponent {
  id: string
  label: string
  available: boolean
  reason: string
}

export default function App() {
  const game = useGame()
  const [replay, setReplay] = useState<string | 'list' | null>(null) // 牌谱文件名,或牌谱列表
  const [watch, setWatch] = useState<{ agents: string[]; name: string } | null>(null) // 正在看的电脑对局
  const [watchError, setWatchError] = useState<string | null>(null)
  const [ladder, setLadder] = useState(false)
  const [insightOn, setInsightOn] = useInsightPreference()

  // 让服务端把四个电脑的一局打完,拿到牌谱名之后在这边按自己的速度放
  const startWatch = async (agents: string[]) => {
    try {
      const r = await fetch('/api/spectate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agents }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail ?? '开不了')
      setWatchError(null)
      setWatch({ agents, name: d.name })
    } catch (e) {
      setWatch(null)
      setWatchError(e instanceof Error ? e.message : '开不了')
    }
  }

  if (watch) {
    return (
      <Viewer
        key={watch.name}
        name={watch.name}
        onClose={() => setWatch(null)}
        watch={{ onNext: () => startWatch(watch.agents) }}
      />
    )
  }
  if (ladder) return <Ladder onClose={() => setLadder(false)} />
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
    return (
      <Lobby
        onStart={game.newMatch}
        onRecords={() => setReplay('list')}
        onWatch={startWatch}
        onLadder={() => setLadder(true)}
        watchError={watchError}
        connected={game.connected}
      />
    )
  }

  const { match, view } = game
  return (
    <div className="room">
      <div className="felt">
        <Table view={view} callouts={game.callouts} onAct={game.act} onActMany={game.actMany} showInsight={insightOn} />
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
        insightOn={insightOn}
        onInsight={setInsightOn}
        onRecords={() => setReplay('list')}
        onQuit={game.quitMatch}
        onHint={game.setHint}
      />
    </div>
  )
}

// ---------------------------------------------------------------- 开始页

const NOTES: Record<string, string> = {
  simple: '能碰就碰、能杠就杠,丢最孤立的牌',
  rule: '会算向听和进张,只在有用的时候碰牌',
  net: '自己训练出来的模型: 先学规则型的打法,再靠自己和自己打来改进',
}
const NAMES: Record<string, string> = { simple: '简单', rule: '规则型', net: '神经网络' }
const FALLBACK: Opponent[] = ['simple', 'rule', 'net'].map((id) => ({
  id,
  label: NAMES[id],
  available: id !== 'net',
  reason: id === 'net' ? '正在检查模型' : '',
}))

interface LobbyProps {
  onStart: (opponent: string) => void
  onRecords: () => void
  onWatch: (agents: string[]) => void
  onLadder: () => void
  watchError: string | null
  connected: boolean
}

function Lobby({ onStart, onRecords, onWatch, onLadder, watchError, connected }: LobbyProps) {
  const [opponent, setOpponent] = useState('rule')
  // 神经网络对手要有模型文件才能选;问一下服务端
  const [list, setList] = useState<Opponent[]>(FALLBACK)
  useEffect(() => {
    fetch('/api/opponents')
      .then((r) => r.json())
      .then(setList)
      .catch(() => setList(FALLBACK.map((o) => (o.id === 'net' ? { ...o, reason: '问不到本地服务' } : o))))
  }, [])
  const netOk = !!list.find((o) => o.id === 'net')?.available
  // 观战的四个座位: 有模型时默认两个神经网络对两个别的
  const [seats, setSeats] = useState<string[] | null>(null)
  const lineup = seats ?? (netOk ? ['net', 'rule', 'simple', 'net'] : ['rule', 'simple', 'rule', 'simple'])

  return (
    <main className="lobby">
      <div className="lobby-card">
        <h1>血战到底</h1>
        <p className="lobby-sub">四川麻将,你和三个电脑。换三张,定缺,打到三家胡牌为止。</p>
        <fieldset className="lobby-options">
          <legend>三个对手的水平</legend>
          {list.map((o) => (
            <label key={o.id} className={!o.available ? 'is-off' : opponent === o.id ? 'is-on' : ''}>
              <input
                type="radio"
                name="opponent"
                value={o.id}
                checked={opponent === o.id}
                disabled={!o.available}
                onChange={() => setOpponent(o.id)}
              />
              <b>{NAMES[o.id] ?? o.label}</b>
              <span>{o.available ? NOTES[o.id] : `现在选不了: ${o.reason || '这个版本没有带模型'}`}</span>
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

        <section className="lobby-watch">
          <h2>看电脑对打</h2>
          <p>四个座位各放一个电脑,牌全部摊开,自动一局接一局地打。能看到模型每一步的想法。</p>
          <div className="lobby-seats">
            {lineup.map((id, s) => (
              <label key={s}>
                <span>{WINDS[s]}</span>
                <select
                  value={id}
                  onChange={(e) => setSeats(lineup.map((old, i) => (i === s ? e.target.value : old)))}
                >
                  {list.map((o) => (
                    <option key={o.id} value={o.id} disabled={!o.available}>
                      {NAMES[o.id] ?? o.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <div className="lobby-buttons">
            <button className="btn" onClick={() => onWatch(lineup)}>
              开始观战
            </button>
            <button className="btn btn-ghost" onClick={onLadder}>
              AI 段位梯
            </button>
          </div>
          {watchError && <p className="lobby-status">观战开不了: {watchError}</p>}
        </section>
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
  insightOn: boolean
  onInsight: (on: boolean) => void
  onRecords: () => void
  onQuit: () => void
  onHint: (on: boolean) => void
}

function Sidebar({ match, view, log, connected, error, insightOn, onInsight, onRecords, onQuit, onHint }: SidebarProps) {
  const me = match.human_seat
  const latest = log.length ? log[log.length - 1] : null

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

      {match.hint_on && (
        <div className="advice">
          <span>模型的建议</span>
          {view.hint ? (
            <>
              <ol>
                {view.hint.choices.map((c) => (
                  <li key={c.id}>
                    <b>{c.text}</b>
                    <i>{Math.round(c.prob * 100)}%</i>
                  </li>
                ))}
              </ol>
              <p>它估计这一局你还能得 {signed(Math.round(view.hint.value * 10) / 10)} 分</p>
            </>
          ) : (
            <p>轮到你时会显示在这里</p>
          )}
        </div>
      )}

      {insightOn && view.insight && <InsightPanel info={view.insight} />}

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
        <SoundToggles />
        <button className="btn" onClick={() => onInsight(!insightOn)} aria-pressed={insightOn}>
          牌理 {insightOn ? '开' : '关'}
        </button>
        {match.hint_available && (
          <button className="btn" onClick={() => onHint(!match.hint_on)} aria-pressed={match.hint_on}>
            提示 {match.hint_on ? '开' : '关'}
          </button>
        )}
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

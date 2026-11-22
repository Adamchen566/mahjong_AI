import { useEffect, useRef, useState } from 'react'
import { defaultSeatLabels, ValueChart } from './Charts'
import { InsightPanel } from './Insight'
import { playEvent } from './sound'
import { Table } from './Table'
import { signed, WINDS } from './tiles'
import { SoundToggles } from './Toggles'
import type { Analysis, GameEvent, RecordStep, RecordSummary, View } from './types'
import type { Callout } from './useGame'

/** 牌谱: 先列出存过的牌局,点开一局后可以一步一步看,四家的牌都是明的。 */
export function Replay({ initial, onClose }: { initial: string | null; onClose: () => void }) {
  const [name, setName] = useState<string | null>(initial)
  if (name) return <Viewer name={name} onBack={() => setName(null)} onClose={onClose} />
  return <RecordList onOpen={setName} onClose={onClose} />
}

function RecordList({ onOpen, onClose }: { onOpen: (name: string) => void; onClose: () => void }) {
  const [records, setRecords] = useState<RecordSummary[] | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    fetch('/api/records')
      .then((r) => r.json())
      .then(setRecords)
      .catch(() => setFailed(true))
  }, [])

  return (
    <main className="lobby">
      <div className="lobby-card lobby-wide">
        <h1>牌谱</h1>
        {failed && <p className="lobby-status">读不到牌谱。确认本地服务还在运行,然后重新打开这一页。</p>}
        {records && records.length === 0 && <p className="lobby-sub">还没有牌谱。打完一局会自动存一份。</p>}
        {records && records.length > 0 && (
          <table className="records">
            <thead>
              <tr>
                <th scope="col">时间</th>
                <th scope="col">局</th>
                <th scope="col">对手</th>
                <th scope="col">你的得分</th>
                <th scope="col">步数</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => {
                const mine = r.scores ? r.scores[r.human_seat] : null
                return (
                  <tr key={r.name}>
                    <td>
                      <button className="link" onClick={() => onOpen(r.name)}>
                        {r.saved_at ? r.saved_at.replace('T', ' ') : r.name}
                      </button>
                    </td>
                    <td>{r.game_no ?? ''}</td>
                    <td>{r.opponent ?? ''}</td>
                    <td className={mine == null ? '' : mine > 0 ? 'up' : mine < 0 ? 'down' : ''}>{mine == null ? '' : signed(mine)}</td>
                    <td>{r.steps}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
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

// ---------------------------------------------------------------- 一局的播放

const SPEEDS = [
  { id: 'slow', name: '慢', ms: 1500 },
  { id: 'normal', name: '中', ms: 850 },
  { id: 'fast', name: '快', ms: 320 },
]

/** 这一步之前要停多久: 换三张、定缺、"过"没什么可看的,一带而过 */
function pauseBefore(next: RecordStep | undefined, base: number): number {
  if (!next) return base
  if (next.type === 'EXCHANGE' || next.type === 'CHOOSE_VOID') return 70
  if (next.type === 'PASS') return 110
  return base
}

/** 把牌谱里的一步变成牌局事件,好让声音和喊话照常工作 */
function eventOf(s: RecordStep): GameEvent | null {
  switch (s.type) {
    case 'DISCARD':
      return { type: 'discard', seat: s.seat, tile: s.tile }
    case 'PONG':
      return { type: 'pong', seat: s.seat }
    case 'MING_GANG':
    case 'AN_GANG':
    case 'JIA_GANG':
      return { type: 'gang', seat: s.seat }
    case 'HU':
      return { type: 'hu', seat: s.seat, zimo: s.zimo }
    default:
      return null
  }
}

const SHOUT: Record<string, string> = { pong: '碰', gang: '杠' }

interface WatchProps {
  /** 这一局打完之后再开一局,返回新牌谱的名字 */
  onNext: () => Promise<void>
}

interface ViewerProps {
  name: string
  onBack?: () => void
  onClose: () => void
  /** 观战: 四个电脑对打,自动播放,打完自动开下一局 */
  watch?: WatchProps
}

export function Viewer({ name, onBack, onClose, watch }: ViewerProps) {
  const [steps, setSteps] = useState<RecordStep[] | null>(null)
  const [step, setStep] = useState(0)
  const [view, setView] = useState<View | null>(null)
  const [shown, setShown] = useState(-1) // 画面上已经是第几步的局面
  const [failed, setFailed] = useState(false)
  const [me, setMe] = useState(0) // 这份牌谱里人坐的座位
  const [seat, setSeat] = useState<number | null>(null) // 坐在下方的是哪一家;null 表示默认
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [playing, setPlaying] = useState(!!watch)
  const [speed, setSpeed] = useState('normal')
  const [loop, setLoop] = useState(true)
  const [callouts, setCallouts] = useState<Callout[]>([])
  const nextId = useRef(1)

  useEffect(() => {
    fetch(`/api/records/${name}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        setSteps(d.steps)
        setMe(d.meta?.human_seat ?? 0)
      })
      .catch(() => setFailed(true))
    // 模型的分析是附加的,拿不到也不影响回放
    fetch(`/api/records/${name}/analysis`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setAnalysis)
      .catch(() => setAnalysis({ available: false, reason: '分析没有算出来' }))
  }, [name])

  const bottom = seat ?? me
  useEffect(() => {
    let stale = false
    fetch(`/api/records/${name}/view/${step}?seat=${bottom}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        if (stale) return
        setView(d.view)
        setShown(step)
      })
      .catch(() => setFailed(true))
    return () => {
      stale = true
    }
  }, [name, step, bottom])

  const total = steps?.length ?? 0
  const go = (n: number) => setStep(Math.max(0, Math.min(total, n)))
  const ended = total > 0 && step >= total

  // 往前走一步时出声、喊话;跳着走(拖进度条、往回退)时不出声
  const last = useRef(0)
  useEffect(() => {
    const from = last.current
    last.current = step
    if (!steps || step !== from + 1) return
    const ev = eventOf(steps[step - 1])
    if (!ev) return
    playEvent(ev, -1)
    const text = ev.type === 'hu' ? (ev.zimo ? '自摸' : '胡') : SHOUT[ev.type]
    if (!text) return
    const id = nextId.current++
    setCallouts((old) => [...old, { id, seat: ev.seat, text }])
    window.setTimeout(() => setCallouts((old) => old.filter((c) => c.id !== id)), 1500)
  }, [step, steps])

  // 自动播放: 等这一步的画面出来之后再计时,不会越跑越快
  useEffect(() => {
    if (!playing || !steps || shown !== step || step >= total) return
    const base = SPEEDS.find((s) => s.id === speed)?.ms ?? 850
    const timer = window.setTimeout(() => setStep((s) => Math.min(total, s + 1)), pauseBefore(steps[step], base))
    return () => window.clearTimeout(timer)
  }, [playing, steps, shown, step, total, speed])

  // 观战: 打完停几秒看结果,然后自动开下一局
  const onNext = watch?.onNext
  useEffect(() => {
    if (!onNext || !ended || !loop || !playing) return
    const timer = window.setTimeout(() => void onNext(), 7000)
    return () => window.clearTimeout(timer)
  }, [onNext, ended, loop, playing])

  // steps[i] 是第 i+1 步;停在第 step 步时,"接下来这一步"就是 steps[step]
  const asteps = analysis?.available ? analysis.steps ?? [] : []
  const upcoming = step < total ? asteps[step] : undefined
  const mine = watch ? undefined : analysis?.summary?.find((s) => s.seat === me)
  const differs = (i: number) => !watch && asteps[i]?.seat === me && asteps[i]?.agree === false
  const nextDiffer = asteps.findIndex((_, i) => i >= step + 1 && differs(i))
  const pct = (p: number) => `${Math.round(p * 100)}%`
  const labels = view?.seat_labels?.map((l, s) => `${WINDS[s]} ${l}`) ?? defaultSeatLabels(me)
  const who = (s: number) => (view?.seat_labels ? labels[s] : s === me ? '你' : WINDS[s])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') setStep((s) => Math.min(total, s + 1))
      if (e.key === 'ArrowLeft') setStep((s) => Math.max(0, s - 1))
      if (e.key === ' ' && !(e.target instanceof HTMLButtonElement)) {
        e.preventDefault()
        setPlaying((p) => !p)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [total])

  // 只在步骤列表内部滚动,让当前这一步可见;不用 scrollIntoView,免得整个页面被带着动
  const listRef = useRef<HTMLOListElement>(null)
  useEffect(() => {
    const list = listRef.current
    const now = list?.querySelector<HTMLElement>('.is-now')
    if (!list || !now) return
    const top = now.offsetTop - list.offsetTop
    if (top < list.scrollTop) list.scrollTop = top
    else if (top + now.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTop = top + now.offsetHeight - list.clientHeight
    }
  }, [step])

  if (failed) {
    return (
      <main className="lobby">
        <div className="lobby-card">
          <h1>{watch ? '观战' : '牌谱'}</h1>
          <p className="lobby-status">这一局打不开。{watch ? '回到开始页重新开一局。' : '文件可能被移走了。'}</p>
          <div className="lobby-buttons">
            <button className="btn btn-ghost" onClick={onBack ?? onClose}>
              {onBack ? '回到牌谱列表' : '回到开始页'}
            </button>
          </div>
        </div>
      </main>
    )
  }

  return (
    <div className="room">
      <div className="felt">
        {view && (
          <Table
            view={view}
            callouts={callouts}
            tileProbs={upcoming && upcoming.seat === bottom ? upcoming.tiles : undefined}
            showInsight={false}
          />
        )}
      </div>
      <aside className="side">
        <header className="side-head">
          <h2>{watch ? '观战' : '回放'}</h2>
          <span>
            第 {step} / {total} 步
          </span>
        </header>
        <div className="replay-controls">
          <button className="btn" onClick={() => go(0)} disabled={step === 0}>
            开头
          </button>
          <button className="btn" onClick={() => go(step - 1)} disabled={step === 0}>
            上一步
          </button>
          <button className="btn" onClick={() => go(step + 1)} disabled={step >= total}>
            下一步
          </button>
          <button className="btn" onClick={() => go(total)} disabled={step >= total}>
            结尾
          </button>
        </div>
        <input
          className="replay-slider"
          type="range"
          min={0}
          max={total}
          value={step}
          onChange={(e) => go(Number(e.target.value))}
          aria-label="跳到第几步"
        />
        <div className="replay-play">
          <button
            className="btn btn-primary"
            onClick={() => {
              if (ended && !watch) go(0)
              setPlaying(!playing)
            }}
            aria-pressed={playing}
          >
            {playing ? '暂停' : ended && !watch ? '从头播放' : '播放'}
          </button>
          <div className="segmented" role="group" aria-label="播放速度">
            {SPEEDS.map((s) => (
              <button key={s.id} className={speed === s.id ? 'is-on' : ''} onClick={() => setSpeed(s.id)} aria-pressed={speed === s.id}>
                {s.name}
              </button>
            ))}
          </div>
        </div>
        {watch && (
          <label className="check">
            <input type="checkbox" checked={loop} onChange={(e) => setLoop(e.target.checked)} />
            打完自动开下一局
          </label>
        )}
        {watch && ended && (
          <div className="latest">
            <span>这一局的结果</span>
            {[0, 1, 2, 3].map((s) => (
              <div key={s} className="result-row">
                {labels[s]}
                <b className={view && view.scores[s] > 0 ? 'up' : view && view.scores[s] < 0 ? 'down' : ''}>
                  {view ? signed(view.scores[s]) : ''}
                </b>
              </div>
            ))}
            <button className="btn" onClick={() => void watch.onNext()}>
              现在就开下一局
            </button>
          </div>
        )}

        <div className="seat-pick">
          <span>坐在下方的是</span>
          <div className="segmented" role="group" aria-label="坐在下方的是哪一家">
            {[0, 1, 2, 3].map((s) => (
              <button key={s} className={bottom === s ? 'is-on' : ''} onClick={() => setSeat(s)} aria-pressed={bottom === s}>
                {WINDS[s]}
              </button>
            ))}
          </div>
        </div>

        {analysis?.available && asteps.length > 0 && (
          <ValueChart steps={asteps} final={analysis.final ?? []} step={step} labels={labels} onJump={go} />
        )}

        <div className="advice">
          <span>模型怎么看</span>
          {!analysis && <p>正在分析这一局</p>}
          {analysis && !analysis.available && <p>没有分析: {analysis.reason}</p>}
          {analysis?.available && (
            <>
              {mine && mine.decisions > 0 && (
                <p>
                  你做了 {mine.decisions} 次选择,其中 {mine.agreed} 次和模型的首选一样。
                </p>
              )}
              {upcoming && !upcoming.forced && upcoming.top && upcoming.chosen && (
                <>
                  <p>接下来轮到{who(upcoming.seat)},模型的想法:</p>
                  <ol>
                    {upcoming.top.map((c) => (
                      <li key={c.id}>
                        <b>{c.text}</b>
                        <i>{pct(c.prob)}</i>
                      </li>
                    ))}
                    <li className={upcoming.agree ? '' : 'is-differ'}>
                      <b>实际{upcoming.agree ? '走的就是第一个' : `走的是${upcoming.chosen.text}`}</b>
                      <i>{upcoming.agree ? '' : pct(upcoming.chosen.prob)}</i>
                    </li>
                  </ol>
                </>
              )}
              {upcoming?.forced && <p>接下来这一步只有一个选择。</p>}
              {!upcoming && <p>这一局已经走完。</p>}
              {!watch && (
                <button className="btn" disabled={nextDiffer < 0} onClick={() => go(nextDiffer)}>
                  {nextDiffer < 0 ? '后面没有和模型不同的选择了' : '跳到你下一处和模型不同的选择'}
                </button>
              )}
            </>
          )}
        </div>

        {view?.insight && <InsightPanel info={view.insight} />}

        <h3>每一步</h3>
        <ol className="log replay-steps" ref={listRef}>
          {steps?.map((s, i) => (
            <li key={i} className={[i + 1 === step ? 'is-now' : '', differs(i) ? 'is-differ' : ''].join(' ')}>
              <button className="link" onClick={() => go(i + 1)}>
                {s.text}
              </button>
            </li>
          ))}
        </ol>
        <footer className="side-foot">
          <SoundToggles />
          {onBack && (
            <button className="btn btn-ghost" onClick={onBack}>
              牌谱列表
            </button>
          )}
          <button className="btn btn-ghost" onClick={onClose}>
            {watch ? '结束观战' : '回到牌桌'}
          </button>
        </footer>
      </aside>
    </div>
  )
}

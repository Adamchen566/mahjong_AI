import { useEffect, useMemo, useRef, useState } from 'react'
import { playRiichiEvent } from '../sound'
import { SoundToggles } from '../Toggles'
import { RTable } from './RiichiApp'
import { DRAW_REASONS, END_REASONS, roundName, signed, WINDS } from './tiles'
import type { RHandResult, RRecordStep, RView } from './types'
import type { RCallout } from './useRiichi'

interface RecordSummary {
  name: string
  saved_at: string | null
  opponent: string | null
  human_seat: number
  steps: number
  scores: number[] | null
}

interface AnalysisStep {
  seat: number
  forced: boolean
  value?: number
  agree?: boolean
  chosen?: { id: number; text: string; prob: number }
  top?: { id: number; text: string; prob: number }[]
  tiles?: [number, number][]
}

interface Analysis {
  available: boolean
  reason?: string
  steps?: AnalysisStep[]
  summary?: { seat: number; decisions: number; agreed: number }[]
}

/** 日麻牌谱: 先列出存过的牌局,点开一场后一步一步看,四家的牌都是明的。 */
export function RReplay({ initial, onClose }: { initial: string | null; onClose: () => void }) {
  const [name, setName] = useState<string | null>(initial)
  if (name) return <RViewer name={name} onBack={() => setName(null)} onClose={onClose} />
  return <RecordList onOpen={setName} onClose={onClose} />
}

function RecordList({ onOpen, onClose }: { onOpen: (name: string) => void; onClose: () => void }) {
  const [records, setRecords] = useState<RecordSummary[] | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    fetch('/api/riichi/records')
      .then((r) => r.json())
      .then(setRecords)
      .catch(() => setFailed(true))
  }, [])
  return (
    <main className="lobby riichi">
      <div className="lobby-card lobby-wide">
        <h1>日麻牌谱</h1>
        {failed && <p className="lobby-status">读不到牌谱。确认本地服务还在运行,然后重新打开这一页。</p>}
        {records && records.length === 0 && <p className="lobby-sub">还没有牌谱。打完一场半庄会自动存一份。</p>}
        {records && records.length > 0 && (
          <table className="records">
            <thead>
              <tr>
                <th scope="col">时间</th>
                <th scope="col">对手</th>
                <th scope="col">你的点数</th>
                <th scope="col">步数</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.name}>
                  <td>
                    <button className="link" onClick={() => onOpen(r.name)}>
                      {r.saved_at ? r.saved_at.replace('T', ' ') : r.name}
                    </button>
                  </td>
                  <td>{r.opponent ?? ''}</td>
                  <td>{r.scores ? r.scores[r.human_seat] : ''}</td>
                  <td>{r.steps}</td>
                </tr>
              ))}
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

const SPEEDS = [
  { id: 'slow', name: '慢', ms: 1300 },
  { id: 'normal', name: '中', ms: 650 },
  { id: 'fast', name: '快', ms: 220 },
]

/** 这一步之前要停多久: "过"一带而过,一局结束多停一会儿 */
function pauseBefore(next: RRecordStep | undefined, prev: RRecordStep | undefined, base: number): number {
  if (prev?.result) return Math.max(base, 2500)
  if (!next) return base
  if (next.type === 'PASS') return 80
  return base
}

/** 把牌谱里的一步变成牌局事件,好让声音和喊话照常工作 */
function eventOf(s: RRecordStep): { type: string; seat: number; tile?: number; result?: RHandResult } | null {
  if (s.result) return { type: 'hand_end', seat: s.seat, result: s.result }
  switch (s.type) {
    case 'DISCARD':
      return { type: 'discard', seat: s.seat, tile: s.tile }
    case 'RIICHI':
      return { type: 'riichi', seat: s.seat }
    case 'CHI':
      return { type: 'chi', seat: s.seat }
    case 'PON':
      return { type: 'pon', seat: s.seat }
    case 'DAIMINKAN':
    case 'ANKAN':
    case 'KAKAN':
      return { type: 'kan', seat: s.seat }
    default:
      return null
  }
}

const SHOUT: Record<string, string> = { riichi: '立直', chi: '吃', pon: '碰', kan: '杠' }

function resultText(r: RHandResult, who: (s: number) => string): string {
  if (r.type === 'win' && r.wins) {
    return r.wins
      .map((w) => {
        const value = w.yakuman ? w.limit : w.limit || `${w.han}番${w.fu}符`
        return `${who(w.seat)} ${w.tsumo ? '自摸' : `荣和${who(w.from_seat)}`} ${value} +${w.gain}(${w.yaku.map(([n]) => n).join('、')})`
      })
      .join(';')
  }
  return DRAW_REASONS[r.reason] ?? r.reason
}

interface ViewerProps {
  name: string
  onBack?: () => void
  onClose: () => void
  /** 观战: 自动播放,打完自动开下一场 */
  watch?: { onNext: () => Promise<void> }
}

export function RViewer({ name, onBack, onClose, watch }: ViewerProps) {
  const [steps, setSteps] = useState<RRecordStep[] | null>(null)
  const [hands, setHands] = useState<{ label: string; start: number }[]>([])
  const [step, setStep] = useState(0)
  const [view, setView] = useState<RView | null>(null)
  const [shown, setShown] = useState(-1)
  const [failed, setFailed] = useState(false)
  const [me, setMe] = useState(0)
  const [seat, setSeat] = useState<number | null>(null)
  const [playing, setPlaying] = useState(!!watch)
  const [speed, setSpeed] = useState(watch ? 'fast' : 'normal')
  const [loop, setLoop] = useState(true)
  const [callouts, setCallouts] = useState<RCallout[]>([])
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const nextId = useRef(1)

  useEffect(() => {
    fetch(`/api/riichi/records/${name}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        setSteps(d.steps)
        setHands(d.hands)
        setMe(d.meta?.human_seat ?? 0)
      })
      .catch(() => setFailed(true))
    fetch(`/api/riichi/records/${name}/analysis`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setAnalysis)
      .catch(() => setAnalysis({ available: false, reason: '分析没有算出来' }))
  }, [name])

  const bottom = seat ?? me
  useEffect(() => {
    let stale = false
    fetch(`/api/riichi/records/${name}/view/${step}?seat=${bottom}`)
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
  const handNow = steps && step > 0 ? steps[step - 1].hand : 0
  const labels = view?.seat_labels?.map((l, s) => `${WINDS[s]} ${l}`)
  const who = (s: number) => (labels ? labels[s] : s === me ? '你' : WINDS[s])

  // 往前走一步时出声、喊话;跳着走时不出声
  const last = useRef(0)
  useEffect(() => {
    const from = last.current
    last.current = step
    if (!steps || step !== from + 1) return
    const s = steps[step - 1]
    const ev = eventOf(s)
    if (!ev) return
    playRiichiEvent(ev, -1)
    const text = ev.type === 'hand_end' ? undefined : SHOUT[ev.type]
    if (!text) return
    const id = nextId.current++
    setCallouts((old) => [...old, { id, seat: ev.seat, text }])
    window.setTimeout(() => setCallouts((old) => old.filter((c) => c.id !== id)), 1500)
  }, [step, steps])

  useEffect(() => {
    if (!playing || !steps || shown !== step || step >= total) return
    const base = SPEEDS.find((s) => s.id === speed)?.ms ?? 650
    const timer = window.setTimeout(
      () => setStep((s) => Math.min(total, s + 1)),
      pauseBefore(steps[step], step > 0 ? steps[step - 1] : undefined, base),
    )
    return () => window.clearTimeout(timer)
  }, [playing, steps, shown, step, total, speed])

  const onNext = watch?.onNext
  useEffect(() => {
    if (!onNext || !ended || !loop || !playing) return
    const timer = window.setTimeout(() => void onNext(), 8000)
    return () => window.clearTimeout(timer)
  }, [onNext, ended, loop, playing])

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

  // 这一局的每一步(只列当前这一局,一场有上千步)
  const handSteps = useMemo(
    () => (steps ? steps.map((s, i) => ({ s, i })).filter(({ s }) => s.hand === handNow) : []),
    [steps, handNow],
  )
  const recent = useMemo(() => {
    if (!steps) return null
    for (let i = step - 1; i >= 0 && steps[i].hand === handNow; i--) if (steps[i].result) return steps[i].result!
    return null
  }, [steps, step, handNow])

  const listRef = useRef<HTMLOListElement>(null)
  useEffect(() => {
    const list = listRef.current
    const now = list?.querySelector<HTMLElement>('.is-now')
    if (!list || !now) return
    const top = now.offsetTop - list.offsetTop
    if (top < list.scrollTop) list.scrollTop = top
    else if (top + now.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = top + now.offsetHeight - list.clientHeight
  }, [step])

  const asteps = analysis?.available ? (analysis.steps ?? []) : []
  const upcoming = step < total ? asteps[step] : undefined
  const mine = watch ? undefined : analysis?.summary?.find((s) => s.seat === me)
  const pct = (p: number) => `${Math.round(p * 100)}%`

  if (failed) {
    return (
      <main className="lobby">
        <div className="lobby-card">
          <h1>{watch ? '观战' : '牌谱'}</h1>
          <p className="lobby-status">这一场打不开。{watch ? '回到开始页重新开一场。' : '文件可能被移走了。'}</p>
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
    <div className="room riichi">
      <div className="felt">{view && <RTable view={view} callouts={callouts} />}</div>
      <aside className="side">
        <header className="side-head">
          <h2>{watch ? '观战' : '日麻回放'}</h2>
          <p>
            {view ? roundName(view) : ''} · 第 {step} / {total} 步
          </p>
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
        <label className="r-hand-pick">
          <span>跳到</span>
          <select value={handNow} onChange={(e) => go(hands[Number(e.target.value)]?.start ?? 0)}>
            {hands.map((h, i) => (
              <option key={i} value={i}>
                {h.label}
              </option>
            ))}
          </select>
        </label>
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
            打完自动开下一场
          </label>
        )}
        {recent && <div className="latest">{resultText(recent, who)}</div>}
        {ended && view?.final && (
          <div className="latest">
            <span>{END_REASONS[view.final.end_reason] ?? view.final.end_reason}</span>
            {[0, 1, 2, 3]
              .sort((a, b) => view.final!.ranks[a] - view.final!.ranks[b])
              .map((s) => (
                <div key={s} className="result-row">
                  {view.final!.ranks[s] + 1}. {who(s)} {view.final!.scores[s]}
                  <b className={view.final!.final_points[s] > 0 ? 'up' : 'down'}>{signed(Math.round(view.final!.final_points[s] * 10) / 10)}</b>
                </div>
              ))}
            {watch && (
              <button className="btn" onClick={() => void watch.onNext()}>
                现在就开下一场
              </button>
            )}
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
        <div className="advice">
          <span>模型怎么看</span>
          {!analysis && <p>正在分析这一场</p>}
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
            </>
          )}
        </div>
        <h3>这一局的每一步</h3>
        <ol className="log replay-steps" ref={listRef}>
          {handSteps.map(({ s, i }) => (
            <li
              key={i}
              className={[i + 1 === step ? 'is-now' : '', !watch && asteps[i]?.seat === me && asteps[i]?.agree === false ? 'is-differ' : ''].join(' ')}
            >
              <button className="link" onClick={() => go(i + 1)}>
                {s.text}
                {s.result ? ` → ${resultText(s.result, who)}` : ''}
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
            {watch ? '结束观战' : '返回'}
          </button>
        </footer>
      </aside>
    </div>
  )
}



import { useEffect, useRef, useState } from 'react'
import { Table } from './Table'
import { signed } from './tiles'
import type { RecordSummary, View } from './types'

interface Step {
  seat: number
  text: string
}

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

function Viewer({ name, onBack, onClose }: { name: string; onBack: () => void; onClose: () => void }) {
  const [steps, setSteps] = useState<Step[] | null>(null)
  const [step, setStep] = useState(0)
  const [view, setView] = useState<View | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    fetch(`/api/records/${name}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setSteps(d.steps))
      .catch(() => setFailed(true))
  }, [name])

  useEffect(() => {
    let stale = false
    fetch(`/api/records/${name}/view/${step}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => !stale && setView(d.view))
      .catch(() => setFailed(true))
    return () => {
      stale = true
    }
  }, [name, step])

  const total = steps?.length ?? 0
  const go = (n: number) => setStep(Math.max(0, Math.min(total, n)))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') setStep((s) => Math.min(total, s + 1))
      if (e.key === 'ArrowLeft') setStep((s) => Math.max(0, s - 1))
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
          <h1>牌谱</h1>
          <p className="lobby-status">这份牌谱打不开,文件可能被移走了。</p>
          <div className="lobby-buttons">
            <button className="btn btn-ghost" onClick={onBack}>
              回到牌谱列表
            </button>
          </div>
        </div>
      </main>
    )
  }

  return (
    <div className="room">
      <div className="felt">{view && <Table view={view} />}</div>
      <aside className="side">
        <header className="side-head">
          <h2>回放</h2>
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
          <button className="btn btn-primary" onClick={() => go(step + 1)} disabled={step >= total}>
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
        <p className="hint">也可以用键盘左右方向键。四家的牌都是明的。</p>
        <h3>每一步</h3>
        <ol className="log replay-steps" ref={listRef}>
          {steps?.map((s, i) => (
            <li key={i} className={i + 1 === step ? 'is-now' : ''}>
              <button className="link" onClick={() => go(i + 1)}>
                {s.text}
              </button>
            </li>
          ))}
        </ol>
        <footer className="side-foot">
          <button className="btn btn-ghost" onClick={onBack}>
            牌谱列表
          </button>
          <button className="btn btn-ghost" onClick={onClose}>
            回到牌桌
          </button>
        </footer>
      </aside>
    </div>
  )
}

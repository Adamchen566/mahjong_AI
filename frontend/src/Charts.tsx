import { useMemo, useState, type MouseEvent } from 'react'
import { signed, WINDS } from './tiles'
import type { AnalysisStep, Ladder } from './types'

/** 四个座位的线色。只用来区分座位,文字仍然用正文的颜色。在深色底上用色觉缺陷模拟验证过相邻两色可分辨。 */
export const SEAT_COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500']

const one = (n: number) => signed(Math.round(n * 10) / 10)
/** 两位小数,带正负号;四舍五入后是 0 的写成 0.00 */
export const two = (n: number) => (Math.abs(n) < 0.005 ? '0.00' : `${n > 0 ? '+' : ''}${n.toFixed(2)}`)

/** 把数值范围放大到好读的刻度 */
function niceBound(v: number): number {
  const steps = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
  return steps.find((s) => s >= v) ?? Math.ceil(v / 100) * 100
}

// ---------------------------------------------------------------- 回放: 模型预计的最终得分

interface ValueChartProps {
  steps: AnalysisStep[]
  final: number[]
  step: number // 现在停在第几步
  labels: string[] // 四个座位的叫法
  onJump: (step: number) => void
}

/**
 * 每一家各一条线: 横轴是步数,纵轴是"这一家已经得的分 + 模型估计它还会得的分"。
 * 线只在这一家做决定的时候有新的点;它最后一次行动之后接到最终得分并走平。
 * 上方的图例同时是读数: 显示光标(或鼠标)所在那一步各家的数值。
 */
export function ValueChart({ steps, final, step, labels, onJump }: ValueChartProps) {
  const total = steps.length
  const [hover, setHover] = useState<number | null>(null)

  const series = useMemo(() => {
    const out: { x: number; y: number }[][] = [[], [], [], []]
    steps.forEach((s, i) => out[s.seat].push({ x: i, y: s.score + s.value }))
    out.forEach((pts, seat) => {
      if (final[seat] == null) return
      // 这一家最后一次行动之后(胡了,或者牌局结束)就不再有估计,直接接到它的最终得分,然后走平
      const last = pts.length ? pts[pts.length - 1].x : 0
      if (last + 1 < total) pts.push({ x: last + 1, y: final[seat] })
      pts.push({ x: total, y: final[seat] })
    })
    return out
  }, [steps, final, total])

  const bound = niceBound(Math.max(1, ...series.flat().map((p) => Math.abs(p.y))))
  const W = 276
  const H = 132
  const pad = { l: 26, r: 6, t: 6, b: 6 }
  const px = (x: number) => pad.l + (x / Math.max(1, total)) * (W - pad.l - pad.r)
  const py = (y: number) => pad.t + ((bound - y) / (2 * bound)) * (H - pad.t - pad.b)
  const at = hover ?? step
  // 某一步时某一家的读数: 它最近一次的估计
  const readout = (seat: number) => {
    const pts = series[seat]
    let v: number | null = null
    for (const p of pts) {
      if (p.x <= at) v = p.y
      else break
    }
    return v ?? pts[0]?.y ?? 0
  }

  const locate = (e: MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - box.left) / box.width) * W
    const s = Math.round(((x - pad.l) / (W - pad.l - pad.r)) * total)
    return Math.max(0, Math.min(total, s))
  }

  return (
    <figure className="chart">
      <figcaption>模型预计各家这一局的最终得分</figcaption>
      <ul className="chart-legend">
        {[0, 1, 2, 3].map((seat) => (
          <li key={seat}>
            <svg width="14" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="14" y2="4" stroke={SEAT_COLORS[seat]} strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span>{labels[seat]}</span>
            <b>{one(readout(seat))}</b>
          </li>
        ))}
      </ul>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="模型预计各家最终得分随牌局进行的变化。点一下跳到那一步。"
        onPointerMove={(e) => setHover(locate(e))}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => onJump(locate(e))}
      >
        {[bound, 0, -bound].map((v) => (
          <g key={v}>
            <line className={v === 0 ? 'chart-zero' : 'chart-grid'} x1={pad.l} x2={W - pad.r} y1={py(v)} y2={py(v)} />
            <text className="chart-tick" x={pad.l - 5} y={py(v) + 3.5} textAnchor="end">
              {signed(v)}
            </text>
          </g>
        ))}
        {series.map((pts, seat) => (
          <polyline
            key={seat}
            fill="none"
            stroke={SEAT_COLORS[seat]}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={pts.map((p) => `${px(p.x).toFixed(1)},${py(p.y).toFixed(1)}`).join(' ')}
          />
        ))}
        <line className="chart-cursor" x1={px(step)} x2={px(step)} y1={pad.t} y2={H - pad.b} />
        {hover != null && hover !== step && (
          <line className="chart-hover" x1={px(hover)} x2={px(hover)} y1={pad.t} y2={H - pad.b} />
        )}
        {[0, 1, 2, 3].map((seat) => (
          <circle key={seat} className="chart-dot" cx={px(at)} cy={py(readout(seat))} r="4" fill={SEAT_COLORS[seat]} />
        ))}
      </svg>
      <p className="chart-note">
        {hover != null ? `第 ${hover} 步` : `第 ${step} 步`}。点图上任意位置跳到那一步。
      </p>
    </figure>
  )
}

export const defaultSeatLabels = (me: number) => [0, 1, 2, 3].map((s) => (s === me ? `${WINDS[s]}(你)` : WINDS[s]))

// ---------------------------------------------------------------- 段位梯: 训练曲线

/** 训练过程中定期和三个规则型 AI 对打的成绩: 一条线加 95% 区间的浅色带。只有一个系列,所以不需要图例。 */
export function TrainingCurve({ curve }: { curve: NonNullable<Ladder['curve']> }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 640
  const H = 220
  const pad = { l: 40, r: 12, t: 10, b: 26 }
  const maxX = Math.max(...curve.map((p) => p.games))
  const maxY = Math.ceil(Math.max(...curve.map((p) => p.hi)) * 2) / 2
  const minY = Math.min(0, Math.floor(Math.min(...curve.map((p) => p.lo)) * 2) / 2)
  const px = (x: number) => pad.l + (x / maxX) * (W - pad.l - pad.r)
  const py = (y: number) => pad.t + ((maxY - y) / (maxY - minY)) * (H - pad.t - pad.b)
  const line = curve.map((p) => `${px(p.games).toFixed(1)},${py(p.score).toFixed(1)}`).join(' ')
  const band =
    curve.map((p) => `${px(p.games).toFixed(1)},${py(p.hi).toFixed(1)}`).join(' ') +
    ' ' +
    [...curve]
      .reverse()
      .map((p) => `${px(p.games).toFixed(1)},${py(p.lo).toFixed(1)}`)
      .join(' ')
  const yTicks: number[] = []
  for (let v = minY; v <= maxY + 1e-9; v += 0.5) yTicks.push(Math.round(v * 10) / 10)
  const xStep = maxX > 6e6 ? 2e6 : maxX > 2e6 ? 1e6 : 5e5
  const xTicks: number[] = []
  for (let v = 0; v <= maxX; v += xStep) xTicks.push(v)
  const wan = (g: number) => `${Math.round(g / 1e4)} 万`
  const shown = hover != null ? curve[hover] : curve[curve.length - 1]

  const locate = (e: MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const games = (((e.clientX - box.left) / box.width) * W - pad.l) / (W - pad.l - pad.r) * maxX
    let best = 0
    curve.forEach((p, i) => {
      if (Math.abs(p.games - games) < Math.abs(curve[best].games - games)) best = i
    })
    return best
  }

  return (
    <figure className="chart chart-wide">
      <figcaption>自我对弈训练过程中,对三个规则型 AI 的平均每局得分</figcaption>
      <p className="chart-readout">
        <b>{two(shown.score)}</b>
        <span>
          {hover != null ? `训练到 ${wan(shown.games)}局时` : `最后一次评估(${wan(shown.games)}局)`},95% 区间{' '}
          {two(shown.lo)} 到 {two(shown.hi)},点炮率{' '}
          {Math.round(shown.deal_in_rate * 100)}%
        </span>
      </p>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="训练曲线: 横轴是累计自我对弈的局数,纵轴是对三个规则型 AI 的平均每局得分"
        onPointerMove={(e) => setHover(locate(e))}
        onPointerLeave={() => setHover(null)}
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line className={v === 0 ? 'chart-zero' : 'chart-grid'} x1={pad.l} x2={W - pad.r} y1={py(v)} y2={py(v)} />
            <text className="chart-tick" x={pad.l - 6} y={py(v) + 3.5} textAnchor="end">
              {v === 0 ? '0' : signed(v)}
            </text>
          </g>
        ))}
        {xTicks.map((v) => (
          <text key={v} className="chart-tick" x={px(v)} y={H - 8} textAnchor="middle">
            {v === 0 ? '0' : wan(v)}
          </text>
        ))}
        <polygon points={band} fill={SEAT_COLORS[0]} opacity="0.12" />
        <polyline points={line} fill="none" stroke={SEAT_COLORS[0]} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {hover != null && <line className="chart-hover" x1={px(shown.games)} x2={px(shown.games)} y1={pad.t} y2={H - pad.b} />}
        <circle className="chart-dot" cx={px(shown.games)} cy={py(shown.score)} r="4" fill={SEAT_COLORS[0]} />
      </svg>
      <p className="chart-note">浅色带是 95% 置信区间。每个点是同一批牌、四个座位各坐一次打出来的。</p>
    </figure>
  )
}

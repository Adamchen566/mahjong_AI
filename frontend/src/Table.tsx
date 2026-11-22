import { useEffect, useMemo, useState } from 'react'
import { relativeOf, SUIT_NAMES, suitOf, tileName, tileSrc, whoIs, WINDS } from './tiles'
import type { HandInfo, Legal, Meld, TileLeft, TileProb, View } from './types'
import type { Callout } from './useGame'

const SHANTEN_TEXT = ['听牌', '一向听', '两向听', '三向听', '四向听', '五向听', '六向听']
/** 向听数的叫法: 0 是听牌,1 是一向听(再进一张有用的牌就听) */
export const shantenText = (n: number) => SHANTEN_TEXT[n] ?? `${n} 向听`

/** 一排小牌,每张下面写着还剩几张 */
export function TileCounts({ items }: { items: TileLeft[] }) {
  return (
    <span className="tile-counts">
      {items.map((u) => (
        <span key={u.tile} className={u.left === 0 ? 'is-gone' : ''} title={`${tileName(u.tile)} 还剩 ${u.left} 张`}>
          <Tile tile={u.tile} size="xs" />
          <i>{u.left}</i>
        </span>
      ))}
    </span>
  )
}

/** 一句话说清一手 13 张牌的牌理 */
export function handInfoText(info: HandInfo): string {
  if (info.shanten === 0) return info.waits?.length ? `听牌,还剩 ${info.total} 张` : '听牌,但要的牌已经没有了'
  return `${shantenText(info.shanten)},进张 ${info.useful?.length ?? 0} 种 ${info.total} 张`
}

// ---------------------------------------------------------------- 牌

export function Tile({ tile, size = 'sm', className = '' }: { tile: number; size?: 'lg' | 'sm' | 'xs'; className?: string }) {
  return <img className={`tile tile-${size} ${className}`} src={tileSrc(tile)} alt={tileName(tile)} draggable={false} />
}

export function Back({ size = 'sm', flat = false }: { size?: 'sm' | 'xs'; flat?: boolean }) {
  return <span className={`back back-${size}${flat ? ' back-flat' : ''}`} aria-hidden="true" />
}

function MeldGroup({ meld }: { meld: Meld }) {
  const n = meld.type === 'PONG' ? 3 : 4
  const label = { PONG: '碰', MING_GANG: '杠', AN_GANG: '暗杠', JIA_GANG: '加杠' }[meld.type]
  return (
    <span className="meld" title={meld.tile == null ? label : `${label} ${tileName(meld.tile)}`}>
      {Array.from({ length: n }, (_, i) =>
        meld.tile == null ? <Back key={i} size="xs" /> : <Tile key={i} tile={meld.tile} size="xs" />,
      )}
    </span>
  )
}

// ---------------------------------------------------------------- 牌桌

interface TableProps {
  view: View
  callouts?: Callout[]
  /** 不传就是只读(回放) */
  onAct?: (id: number) => void
  onActMany?: (ids: number[]) => void
  /** 模型对下方这一家"打哪张"的看法,画成手牌上方的概率条。不传时用对局提示里的 */
  tileProbs?: TileProb[]
  /** 在手牌上标出每张牌打出去之后的进张数 */
  showInsight?: boolean
}

export function Table({ view, callouts = [], onAct, onActMany, tileProbs, showInsight = true }: TableProps) {
  const me = view.seat
  const seats = [0, 1, 2, 3].map((rel) => (me + rel) % 4) // 下、右、上、左
  const lastDiscard = view.pending_discard && !view.pending_discard.rob_kong ? view.pending_discard : null

  return (
    <div className="table">
      {seats.slice(1).map((seat) => (
        <Opponent key={seat} view={view} seat={seat} callouts={callouts} />
      ))}

      <div className="middle">
        {seats.map((seat) => {
          const pos = ['bottom', 'right', 'top', 'left'][relativeOf(seat, me)]
          const pile = view.discards[seat]
          return (
            <div key={seat} className={`pile pile-${pos}`} aria-label={`${whoIs(seat, me)}的弃牌`}>
              {pile.map((t, i) => (
                <Tile
                  key={i}
                  tile={t}
                  size="xs"
                  className={lastDiscard && lastDiscard.seat === seat && i === pile.length - 1 ? 'tile-last' : ''}
                />
              ))}
            </div>
          )
        })}
        <Well view={view} />
      </div>

      <Self
        view={view}
        callouts={callouts}
        onAct={onAct}
        onActMany={onActMany}
        tileProbs={tileProbs ?? view.hint?.tiles}
        showInsight={showInsight}
      />
    </div>
  )
}

/** 牌桌中央: 四个风位、谁在行动、谁坐庄、各家缺哪门、还剩多少牌 */
function Well({ view }: { view: View }) {
  const me = view.seat
  return (
    <div className="well">
      {[0, 1, 2, 3].map((seat) => {
        const pos = ['bottom', 'right', 'top', 'left'][relativeOf(seat, me)]
        const voidSuit = view.void[seat]
        const cls = [
          'seatmark',
          `seatmark-${pos}`,
          view.current === seat ? 'is-active' : '',
          view.won[seat] ? 'is-out' : '',
        ].join(' ')
        return (
          <div key={seat} className={cls} title={whoIs(seat, me)}>
            <span className="seatmark-wind">
              {WINDS[seat]}
              {view.dealer === seat && <i className="badge badge-primary dealer">庄</i>}
            </span>
            {voidSuit != null && <VoidMark suit={voidSuit} />}
          </div>
        )
      })}
      <div className="wall">
        <b>{view.wall_remaining}</b>
        <span>张余牌</span>
      </div>
    </div>
  )
}

/** 缺哪门: 这门花色的符号加一道斜杠。万是红色的"万",筒是蓝色的圆饼,条是绿色的竹节。 */
function VoidMark({ suit }: { suit: number }) {
  const label = `缺${SUIT_NAMES[suit]}`
  return (
    <span className={`voidmark voidmark-${suit}`} role="img" aria-label={label} title={label}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        {suit === 0 && (
          <text x="12" y="17.2" textAnchor="middle" fontSize="14.5" fontWeight="700">
            万
          </text>
        )}
        {suit === 1 && (
          <>
            <circle className="outline" cx="12" cy="12" r="6.6" />
            <circle cx="12" cy="12" r="2.6" />
          </>
        )}
        {suit === 2 && (
          <>
            <rect x="10" y="4" width="4" height="7" rx="1.6" />
            <rect x="10" y="13" width="4" height="7" rx="1.6" />
            <rect x="8.2" y="11" width="7.6" height="2" rx="1" />
          </>
        )}
        <path className="slash-gap" d="M5 19 19 5" />
        <path className="slash" d="M5 19 19 5" />
      </svg>
    </span>
  )
}

function Plate({ view, seat }: { view: View; seat: number }) {
  const me = view.seat
  const win = view.wins.find((w) => w.seat === seat)
  const score = view.scores[seat]
  const shanten = view.shanten?.[seat]
  return (
    <div className={`plate${view.current === seat ? ' plate-active' : ''}`}>
      <span className="plate-name">{view.seat_labels?.[seat] ?? whoIs(seat, me)}</span>
      <span className="plate-wind">{WINDS[seat]}</span>
      {win && <span className="plate-won">已胡{win.tile != null && <Tile tile={win.tile} size="xs" />}</span>}
      {!win && shanten != null && (
        <span className={`plate-shanten${shanten === 0 ? ' is-ready' : ''}`}>{shantenText(shanten)}</span>
      )}
      <span className={`plate-score${score > 0 ? ' up' : score < 0 ? ' down' : ''}`}>{score > 0 ? `+${score}` : score}</span>
    </div>
  )
}

function Shouts({ callouts, seat }: { callouts: Callout[]; seat: number }) {
  const mine = callouts.filter((c) => c.seat === seat)
  if (!mine.length) return null
  return (
    <span className="shout" role="status">
      {mine[mine.length - 1].text}
    </span>
  )
}

function Opponent({ view, seat, callouts }: { view: View; seat: number; callouts: Callout[] }) {
  const pos = ['bottom', 'right', 'top', 'left'][relativeOf(seat, view.seat)]
  const open = view.hands?.[seat]
  const side = pos !== 'top'
  return (
    <div className={`opp opp-${pos}`}>
      <Plate view={view} seat={seat} />
      <div className="opp-tiles">
        <div className={`opp-hand${open ? ' is-open' : ''}`}>
          {open
            ? open.map((t, i) => <Tile key={i} tile={t} size="xs" />)
            : Array.from({ length: view.hand_sizes[seat] }, (_, i) => <Back key={i} size="xs" flat={side} />)}
        </div>
        {view.melds[seat].length > 0 && (
          <div className="opp-melds">
            {view.melds[seat].map((m, i) => (
              <MeldGroup key={i} meld={m} />
            ))}
          </div>
        )}
      </div>
      <Shouts callouts={callouts} seat={seat} />
    </div>
  )
}

// ---------------------------------------------------------------- 自己

function Self({
  view,
  callouts,
  onAct,
  onActMany,
  tileProbs,
  showInsight,
}: Omit<TableProps, 'callouts'> & { callouts: Callout[] }) {
  const me = view.seat
  const legal = view.legal
  const myTurn = legal.length > 0 && !!onAct
  const [selected, setSelected] = useState<number[]>([]) // 选中的手牌位置

  // 手牌: 刚摸的那张单独放在最右边
  const { tiles, drawnIndex } = useMemo(() => {
    const sorted = [...view.hand]
    let drawnIndex = -1
    if (view.drawn != null) {
      const at = sorted.lastIndexOf(view.drawn)
      if (at >= 0) {
        sorted.splice(at, 1)
        sorted.push(view.drawn)
        drawnIndex = sorted.length - 1
      }
    }
    return { tiles: sorted, drawnIndex }
  }, [view.hand, view.drawn])

  const handKey = `${view.phase}|${view.hand.join(',')}|${legal.length}`
  useEffect(() => setSelected([]), [handKey])

  const byType = (type: Legal['type']) => legal.filter((a) => a.type === type)
  const discards = new Set(byType('DISCARD').map((a) => a.tile))
  const exchanging = myTurn && view.phase === 'EXCHANGE'
  const exchangeTiles = new Set(byType('EXCHANGE').map((a) => a.tile))
  const exchangeSuit = selected.length ? suitOf(tiles[selected[0]]) : null

  const canPick = (i: number) => {
    const t = tiles[i]
    if (exchanging) {
      if (selected.includes(i)) return true
      if (selected.length >= 3) return false
      return exchangeSuit == null ? exchangeTiles.has(t) : suitOf(t) === exchangeSuit
    }
    return myTurn && view.phase === 'TURN' && discards.has(t)
  }

  const click = (i: number) => {
    if (!canPick(i)) return
    if (exchanging) {
      setSelected((old) => (old.includes(i) ? old.filter((x) => x !== i) : [...old, i]))
    } else if (selected[0] === i) {
      onAct?.(tiles[i]) // 出牌动作的编号就是牌的编号
    } else {
      setSelected([i])
    }
  }

  const voidSuit = view.void[me]
  // 模型的首选如果是打出或换出某张牌,在手牌上把那张标出来
  const top = view.hint?.choices[0]
  const hintIndex = top && (top.type === 'DISCARD' || top.type === 'EXCHANGE') ? tiles.indexOf(top.tile) : -1

  // 概率条: 同一种牌有好几张时只画在第一张上(概率是对"这种牌"说的)
  const probOf = new Map(tileProbs ?? [])
  const maxProb = Math.max(0, ...probOf.values())
  const firstAt = (i: number) => tiles.indexOf(tiles[i]) === i
  // 牌理: 轮到自己出牌时,每张牌打出去之后的向听数和进张
  const rated = showInsight && view.phase === 'TURN' ? view.insight?.discards : undefined
  const ratingOf = new Map((rated ?? []).map((o) => [o.tile, o]))
  const bestShanten = view.insight?.shanten

  return (
    <div className="self">
      <div className="self-bar">
        <Plate view={view} seat={me} />
        <Shouts callouts={callouts} seat={me} />
        {myTurn && (
          <Actions
            view={view}
            legal={legal}
            tiles={tiles}
            selected={selected}
            onAct={onAct!}
            onActMany={onActMany!}
            rating={selected.length === 1 ? ratingOf.get(tiles[selected[0]]) : undefined}
          />
        )}
        {!myTurn && view.phase !== 'END' && !view.hands && <p className="hint">{waitingText(view)}</p>}
      </div>

      <div className="self-row">
        {view.melds[me].length > 0 && (
          <div className="self-melds">
            {view.melds[me].map((m, i) => (
              <MeldGroup key={i} meld={m} />
            ))}
          </div>
        )}
        <div className={`hand${probOf.size ? ' has-probs' : ''}`} role="group" aria-label="手牌">
          {tiles.map((t, i) => {
            const pickable = canPick(i)
            const prob = firstAt(i) ? probOf.get(t) : undefined
            const rating = firstAt(i) ? ratingOf.get(t) : undefined
            const keeps = rating && rating.shanten === bestShanten
            const cls = [
              'hand-tile',
              selected.includes(i) ? 'is-selected' : '',
              i === drawnIndex ? 'is-drawn' : '',
              i === hintIndex ? 'is-hinted' : '',
              myTurn && (view.phase === 'TURN' || exchanging) && !pickable ? 'is-locked' : '',
              voidSuit != null && suitOf(t) === voidSuit ? 'is-void' : '',
            ].join(' ')
            return (
              <button
                key={i}
                type="button"
                className={cls}
                disabled={!pickable}
                onClick={() => click(i)}
                aria-label={tileName(t)}
                aria-pressed={selected.includes(i)}
              >
                <Tile tile={t} size="lg" />
                {prob != null && (
                  <span
                    className={`prob${prob === maxProb ? ' is-top' : ''}`}
                    style={{ height: `${Math.max(2, Math.round(prob * 26))}px` }}
                    title={`模型打出这张的概率 ${Math.round(prob * 100)}%`}
                  >
                    {prob === maxProb && <i>{Math.round(prob * 100)}%</i>}
                  </span>
                )}
                {keeps && (
                  <span
                    className={`tip${rating.best ? ' is-best' : ''}`}
                    title={`打出后${handInfoText(rating)}`}
                  >
                    {rating.shanten === 0 ? `听${rating.total}` : rating.total}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function waitingText(view: View) {
  if (view.phase === 'EXCHANGE') return '等其他人选好要换的牌'
  if (view.phase === 'CHOOSE_VOID') return '等其他人定缺'
  if (view.won[view.seat]) return '你已经胡了,看其他三家打完'
  return `${whoIs(view.current, view.seat)}在想`
}

// ---------------------------------------------------------------- 操作区

interface ActionsProps {
  view: View
  legal: Legal[]
  tiles: number[]
  selected: number[]
  onAct: (id: number) => void
  onActMany: (ids: number[]) => void
  /** 选中的那张牌打出去之后的牌理 */
  rating?: HandInfo
}

function Actions({ view, legal, tiles, selected, onAct, onActMany, rating }: ActionsProps) {
  const find = (type: Legal['type']) => legal.find((a) => a.type === type)
  const all = (type: Legal['type']) => legal.filter((a) => a.type === type)

  if (view.phase === 'EXCHANGE') {
    const ids = selected.map((i) => all('EXCHANGE').find((a) => a.tile === tiles[i])?.id ?? 88 + tiles[i])
    return (
      <div className="actions">
        <p className="hint">选三张同一花色的牌换出去(已选 {selected.length} 张)</p>
        <button className="btn btn-primary" disabled={selected.length !== 3} onClick={() => onActMany(ids)}>
          换出这三张
        </button>
      </div>
    )
  }

  if (view.phase === 'CHOOSE_VOID') {
    const count = (suit: number) => view.hand.filter((t) => suitOf(t) === suit).length
    return (
      <div className="actions">
        <p className="hint">
          定缺: 选一门不要的花色
          {view.exchange.received.length > 0 && (
            <span className="received">
              刚换到
              {view.exchange.received.map((t, i) => (
                <Tile key={i} tile={t} size="xs" />
              ))}
            </span>
          )}
        </p>
        {all('CHOOSE_VOID').map((a) => (
          <button key={a.id} className="btn" onClick={() => onAct(a.id)}>
            缺{SUIT_NAMES[a.tile]}
            <small>手里 {count(a.tile)} 张</small>
          </button>
        ))}
      </div>
    )
  }

  if (view.phase === 'TURN') {
    const hu = find('HU')
    const gangs = [...all('AN_GANG'), ...all('JIA_GANG')]
    const chosen = selected.length === 1 ? tiles[selected[0]] : null
    return (
      <div className="actions">
        {hu && (
          <button className="btn btn-primary btn-big" onClick={() => onAct(hu.id)}>
            自摸
          </button>
        )}
        {gangs.map((a) => (
          <button key={a.id} className="btn" onClick={() => onAct(a.id)}>
            {a.type === 'AN_GANG' ? '暗杠' : '加杠'}
            <Tile tile={a.tile} size="xs" />
          </button>
        ))}
        {chosen != null ? (
          <>
            <button className={hu ? 'btn' : 'btn btn-primary'} onClick={() => onAct(chosen)}>
              打出 {tileName(chosen)}
            </button>
            {rating && (
              <p className="hint">
                打出后{handInfoText(rating)}
                <TileCounts items={rating.waits ?? rating.useful ?? []} />
              </p>
            )}
          </>
        ) : (
          <p className="hint">{mustVoid(view) ? '先把缺门的牌打完。' : ''}点一张牌选中,再点一次打出</p>
        )}
      </div>
    )
  }

  // RESPONSE / ROB_KONG: 别人打出(或加杠)了一张牌
  const pending = view.pending_discard
  const hu = find('HU')
  const gang = find('MING_GANG')
  const pong = find('PONG')
  const pass = find('PASS')
  return (
    <div className="actions">
      {pending && (
        <p className="hint">
          {whoIs(pending.seat, view.seat)}
          {pending.rob_kong ? '要加杠' : '打出'}
          <Tile tile={pending.tile} size="xs" />
        </p>
      )}
      {hu && (
        <button className="btn btn-primary btn-big" onClick={() => onAct(hu.id)}>
          {pending?.rob_kong ? '抢杠胡' : '胡'}
        </button>
      )}
      {gang && (
        <button className="btn" onClick={() => onAct(gang.id)}>
          杠
        </button>
      )}
      {pong && (
        <button className="btn" onClick={() => onAct(pong.id)}>
          碰
        </button>
      )}
      {pass && (
        <button className="btn btn-ghost" onClick={() => onAct(pass.id)}>
          过
        </button>
      )}
    </div>
  )
}

function mustVoid(view: View) {
  const v = view.void[view.seat]
  return v != null && view.hand.some((t) => suitOf(t) === v)
}

import { useEffect, useMemo, useState } from 'react'
import { Back } from '../Table'
import './riichi.css'
import {
  DRAW_REASONS,
  END_REASONS,
  kindOf,
  relativeOf,
  roundName,
  seatWind,
  signed,
  sortKey,
  tileName,
  tileSrc,
  whoIs,
} from './tiles'
import type { RLegal, RMatchInfo, RMeld, RView, RWin } from './types'
import { useRiichi, type RCallout, type RLogged } from './useRiichi'

const POS = ['bottom', 'right', 'top', 'left'] as const
const SHANTEN_TEXT = ['听牌', '一向听', '两向听', '三向听', '四向听', '五向听', '六向听']
const shantenText = (n: number) => (n < 0 ? '和了' : (SHANTEN_TEXT[n] ?? `${n} 向听`))

/** 日本麻将(立直麻将)的整套页面: 开始页、牌桌、每局结算、终局名次。和川麻的页面互不影响。 */
export function RiichiApp({ onClose }: { onClose: () => void }) {
  const game = useRiichi()
  useEffect(() => {
    const old = document.title
    document.title = '日本麻将'
    return () => {
      document.title = old
    }
  }, [])

  if (!game.ready) {
    return (
      <main className="lobby">
        <p className="lobby-status">正在连接本地服务</p>
      </main>
    )
  }
  if (!game.match || !game.view) {
    return <RLobby onStart={game.newMatch} onClose={onClose} connected={game.connected} />
  }
  const { match, view } = game
  return (
    <div className="room riichi">
      <div className="felt">
        <RTable view={view} callouts={game.callouts} onAct={game.act} />
        {match.over && view.final ? (
          <FinalResult view={view} onAgain={() => game.newMatch(match.opponent)} onQuit={game.quitMatch} />
        ) : (
          match.paused && view.result && <HandResult view={view} onNext={game.resume} />
        )}
      </div>
      <RSidebar
        match={match}
        view={view}
        log={game.log}
        connected={game.connected}
        error={game.error}
        onQuit={() => {
          game.quitMatch()
        }}
        onClose={onClose}
      />
    </div>
  )
}

// ---------------------------------------------------------------- 开始页

function RLobby({ onStart, onClose, connected }: { onStart: (o: string) => void; onClose: () => void; connected: boolean }) {
  const [opponent, setOpponent] = useState('shanten')
  const options = [
    { id: 'shanten', label: '规则型', note: '看向听数和进张出牌,听牌就立直,别人立直时会弃和' },
    { id: 'simple', label: '简单', note: '不吃不碰不立直,丢最孤立的牌' },
  ]
  return (
    <main className="lobby">
      <div className="lobby-card">
        <h1>日本麻将</h1>
        <p className="lobby-sub">
          立直麻将,天凤段位战规则: 四人半庄,有赤宝牌和喰断。你和三个电脑,从东一局打到南四局。
        </p>
        <fieldset className="lobby-options">
          <legend>电脑对手</legend>
          {options.map((o) => (
            <label key={o.id} className={opponent === o.id ? 'is-on' : ''}>
              <input
                type="radio"
                name="riichi-opponent"
                value={o.id}
                checked={opponent === o.id}
                onChange={() => setOpponent(o.id)}
              />
              <b>{o.label}</b>
              <span>{o.note}</span>
            </label>
          ))}
        </fieldset>
        <div className="lobby-buttons">
          <button className="btn btn-primary btn-big" disabled={!connected} onClick={() => onStart(opponent)}>
            开始一场
          </button>
          <button className="btn btn-ghost" onClick={onClose}>
            回到四川麻将
          </button>
        </div>
        {!connected && <p className="lobby-status">和本地服务断开了,正在重连</p>}
      </div>
    </main>
  )
}

// ---------------------------------------------------------------- 牌

export function RTile({ tile, size = 'xs', className = '' }: { tile: number; size?: 'lg' | 'xs'; className?: string }) {
  return (
    <img className={`tile tile-${size} ${className}`} src={tileSrc(tile)} alt={tileName(tile)} draggable={false} />
  )
}

const MELD_LABEL = { CHI: '吃', PON: '碰', DAIMINKAN: '杠', ANKAN: '暗杠', KAKAN: '加杠' }

function RMeldGroup({ meld }: { meld: RMeld }) {
  const tiles = [...meld.tiles].sort((a, b) => sortKey(a) - sortKey(b))
  return (
    <span className="meld" title={`${MELD_LABEL[meld.type]} ${tileName(meld.tiles[0])}`}>
      {tiles.map((t, i) =>
        meld.type === 'ANKAN' && (i === 0 || i === 3) ? (
          <Back key={i} size="xs" />
        ) : (
          <RTile key={i} tile={t} className={t === meld.called && meld.type !== 'ANKAN' ? 'is-called-in' : ''} />
        ),
      )}
    </span>
  )
}

// ---------------------------------------------------------------- 牌桌

function RTable({ view, callouts, onAct }: { view: RView; callouts: RCallout[]; onAct: (id: number) => void }) {
  const me = view.seat
  const seats = [0, 1, 2, 3].map((rel) => (me + rel) % 4)
  const pending = view.pending && view.pending.kind === 'discard' ? view.pending : null
  return (
    <div className="table">
      {seats.slice(1).map((seat) => (
        <ROpponent key={seat} view={view} seat={seat} callouts={callouts} />
      ))}
      <div className="middle">
        {seats.map((seat) => {
          const pos = POS[relativeOf(seat, me)]
          const pile = view.discards[seat]
          const flags = view.discard_flags[seat]
          return (
            <div key={seat} className={`pile pile-${pos}`} aria-label={`${whoIs(seat, me)}的弃牌`}>
              {pile.map((t, i) => {
                const [tsumogiri, riichi, called] = flags[i]
                const cls = [
                  riichi ? 'is-riichi-tile' : '',
                  called ? 'is-called' : '',
                  tsumogiri ? 'is-tsumogiri' : '',
                  pending && pending.seat === seat && i === pile.length - 1 ? 'tile-last' : '',
                ].join(' ')
                return <RTile key={i} tile={t} className={cls} />
              })}
            </div>
          )
        })}
        <RWell view={view} />
      </div>
      <RSelf view={view} callouts={callouts} onAct={onAct} />
    </div>
  )
}

/** 牌桌中央: 第几局、本场和供托、宝牌指示牌、余牌、四家的自风和立直棒 */
function RWell({ view }: { view: RView }) {
  const me = view.seat
  return (
    <div className="well r-well">
      {[0, 1, 2, 3].map((seat) => {
        const pos = POS[relativeOf(seat, me)]
        const cls = ['seatmark', `seatmark-${pos}`, view.current === seat ? 'is-active' : ''].join(' ')
        return (
          <div key={seat} className={cls} title={whoIs(seat, me)}>
            <span className="seatmark-wind">
              {seatWind(seat, view.dealer)}
              {view.dealer === seat && <i className="badge badge-primary dealer">庄</i>}
            </span>
            {view.riichi[seat] > 0 && <span className="r-stick" title="立直" />}
          </div>
        )
      })}
      <div className="wall r-center">
        <b className="r-round">{roundName({ ...view, honba: 0 })}</b>
        <span className="r-counters">
          {view.honba}本场 · 供托 {view.sticks}
        </span>
        <span className="r-dora" title="宝牌指示牌">
          {view.dora_indicators.map((t, i) => (
            <RTile key={i} tile={t} />
          ))}
        </span>
        <span className="r-wall">余 {view.wall_remaining}</span>
      </div>
    </div>
  )
}

function Plate({ view, seat }: { view: RView; seat: number }) {
  const me = view.seat
  return (
    <div className={`plate${view.current === seat ? ' plate-active' : ''}`}>
      <span className="plate-name">{whoIs(seat, me)}</span>
      <span className="plate-wind">{seatWind(seat, view.dealer)}</span>
      {view.riichi[seat] > 0 && <span className="r-riichi-badge">{view.riichi[seat] === 2 ? '双立直' : '立直'}</span>}
      <span className="plate-score">{view.scores[seat]}</span>
    </div>
  )
}

function Shouts({ callouts, seat }: { callouts: RCallout[]; seat: number }) {
  const mine = callouts.filter((c) => c.seat === seat)
  if (!mine.length) return null
  return (
    <span className="shout" role="status">
      {mine[mine.length - 1].text}
    </span>
  )
}

function ROpponent({ view, seat, callouts }: { view: RView; seat: number; callouts: RCallout[] }) {
  const pos = POS[relativeOf(seat, view.seat)]
  const side = pos !== 'top'
  return (
    <div className={`opp opp-${pos}`}>
      <Plate view={view} seat={seat} />
      <div className="opp-tiles">
        <div className="opp-hand">
          {Array.from({ length: view.hand_sizes[seat] }, (_, i) => (
            <Back key={i} size="xs" flat={side} />
          ))}
        </div>
        {view.melds[seat].length > 0 && (
          <div className="opp-melds">
            {view.melds[seat].map((m, i) => (
              <RMeldGroup key={i} meld={m} />
            ))}
          </div>
        )}
      </div>
      <Shouts callouts={callouts} seat={seat} />
    </div>
  )
}

// ---------------------------------------------------------------- 自己

function RSelf({ view, callouts, onAct }: { view: RView; callouts: RCallout[]; onAct: (id: number) => void }) {
  const me = view.seat
  const legal = view.legal
  const myTurn = legal.length > 0
  const [selected, setSelected] = useState<number | null>(null)

  // 手牌排好序,刚摸的那张放在最右边
  const { tiles, drawnIndex } = useMemo(() => {
    const sorted = [...view.hand].sort((a, b) => sortKey(a) - sortKey(b))
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
  useEffect(() => setSelected(null), [handKey])

  const discardable = new Set(legal.filter((a) => a.type === 'DISCARD').map((a) => a.tile))
  const choosing = myTurn && (view.phase === 'TURN' || view.phase === 'RIICHI')
  const rated = view.insight?.discards
  const firstAt = (i: number) => tiles.findIndex((t) => kindOf(t) === kindOf(tiles[i])) === i

  const click = (i: number) => {
    if (!choosing || !discardable.has(tiles[i])) return
    if (selected === i) onAct(tiles[i]) // 出牌动作的编号就是牌的编号
    else setSelected(i)
  }

  return (
    <div className="self">
      <div className="self-bar">
        <Plate view={view} seat={me} />
        <Shouts callouts={callouts} seat={me} />
        {myTurn ? (
          <RActions view={view} legal={legal} chosen={selected != null ? tiles[selected] : null} onAct={onAct} />
        ) : (
          view.phase !== 'END' && <p className="hint">{whoIs(view.current, me)}在想</p>
        )}
        {view.furiten && <span className="badge r-furiten">振听</span>}
      </div>
      <div className="self-row">
        {view.melds[me].length > 0 && (
          <div className="self-melds">
            {view.melds[me].map((m, i) => (
              <RMeldGroup key={i} meld={m} />
            ))}
          </div>
        )}
        <div className="hand" role="group" aria-label="手牌">
          {tiles.map((t, i) => {
            const pickable = choosing && discardable.has(t)
            const rating = rated && firstAt(i) ? rated[String(kindOf(t))] : undefined
            const cls = [
              'hand-tile',
              selected === i ? 'is-selected' : '',
              i === drawnIndex ? 'is-drawn' : '',
              choosing && !pickable ? 'is-locked' : '',
            ].join(' ')
            return (
              <button
                key={i}
                type="button"
                className={cls}
                disabled={!pickable}
                onClick={() => click(i)}
                aria-label={tileName(t)}
                aria-pressed={selected === i}
              >
                <RTile tile={t} size="lg" />
                {choosing && rating && (
                  <span className={`tip${rating.best ? ' is-best' : ''}`} title={`打出后${shantenText(rating.shanten)},进张 ${rating.total} 张`}>
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

function TilesInline({ tiles }: { tiles: number[] }) {
  return (
    <span className="r-inline">
      {tiles.map((t, i) => (
        <RTile key={i} tile={t} />
      ))}
    </span>
  )
}

function RActions({
  view,
  legal,
  chosen,
  onAct,
}: {
  view: RView
  legal: RLegal[]
  chosen: number | null
  onAct: (id: number) => void
}) {
  const all = (type: RLegal['type']) => legal.filter((a) => a.type === type)
  const one = (type: RLegal['type']) => legal.find((a) => a.type === type)
  const me = view.seat

  if (view.phase === 'RIICHI') {
    return (
      <div className="actions">
        <p className="hint">立直: 选一张打出(只能选打出后仍然听牌的牌),点两次打出</p>
        {chosen != null && (
          <button className="btn btn-primary" onClick={() => onAct(chosen)}>
            立直,打出 {tileName(chosen)}
          </button>
        )}
      </div>
    )
  }

  if (view.phase === 'TURN') {
    const tsumo = one('TSUMO')
    const riichi = one('RIICHI')
    const kyuushu = one('KYUUSHU')
    const kans = [...all('ANKAN'), ...all('KAKAN')]
    const primaryTaken = !!tsumo
    return (
      <div className="actions">
        {tsumo && (
          <button className="btn btn-primary btn-big" onClick={() => onAct(tsumo.id)}>
            自摸
          </button>
        )}
        {riichi && (
          <button className={primaryTaken ? 'btn' : 'btn btn-primary'} onClick={() => onAct(riichi.id)}>
            立直
          </button>
        )}
        {kans.map((a) => (
          <button key={a.id} className="btn" onClick={() => onAct(a.id)}>
            {a.type === 'ANKAN' ? '暗杠' : '加杠'}
            <RTile tile={a.tile} />
          </button>
        ))}
        {kyuushu && (
          <button className="btn" onClick={() => onAct(kyuushu.id)}>
            九种九牌(流局)
          </button>
        )}
        {chosen != null ? (
          <button className="btn" onClick={() => onAct(chosen)}>
            打出 {tileName(chosen)}
          </button>
        ) : (
          <p className="hint">
            {view.riichi[me] ? '已立直: 只能打刚摸的牌。' : view.kuikae.length ? '刚吃碰过,不能马上打同一种牌。' : ''}
            点一张牌选中,再点一次打出
          </p>
        )}
      </div>
    )
  }

  // RESPONSE / ROB_KAN
  const pending = view.pending
  const ron = one('RON')
  const pass = one('PASS')
  return (
    <div className="actions">
      {pending && (
        <p className="hint">
          {whoIs(pending.seat, me)}
          {pending.kind === 'discard' ? '打出' : '要杠'}
          <RTile tile={pending.tile} />
        </p>
      )}
      {ron && (
        <button className="btn btn-primary btn-big" onClick={() => onAct(ron.id)}>
          {view.phase === 'ROB_KAN' ? '抢杠' : '荣和'}
        </button>
      )}
      {all('PON').map((a) => (
        <button key={a.id} className="btn" onClick={() => onAct(a.id)} title={a.text}>
          碰 <TilesInline tiles={a.uses ?? []} />
        </button>
      ))}
      {all('CHI').map((a) => (
        <button key={a.id} className="btn" onClick={() => onAct(a.id)} title={a.text}>
          吃 <TilesInline tiles={a.uses ?? []} />
        </button>
      ))}
      {one('DAIMINKAN') && (
        <button className="btn" onClick={() => onAct(one('DAIMINKAN')!.id)}>
          杠
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

// ---------------------------------------------------------------- 结算

function WinBlock({ win, me }: { win: RWin; me: number }) {
  const value = win.yakuman ? win.limit : win.limit ? `${win.han} 番 ${win.limit}` : `${win.han} 番 ${win.fu} 符`
  const tiles = [...win.hand].sort((a, b) => sortKey(a) - sortKey(b))
  if (win.tsumo) tiles.splice(tiles.lastIndexOf(win.tile), 1)
  return (
    <div className="r-win">
      <p className="r-win-head">
        <b>{whoIs(win.seat, me)}</b> {win.tsumo ? '自摸' : `荣和(${whoIs(win.from_seat, me)}放铳)`}
        <span className="r-win-value">{value}</span>
        <span className="up">+{win.gain}</span>
      </p>
      <div className="r-win-hand">
        {tiles.map((t, i) => (
          <RTile key={i} tile={t} />
        ))}
        <RTile tile={win.tile} className="r-win-tile" />
        {win.melds.map((m, i) => (
          <RMeldGroup key={i} meld={m} />
        ))}
      </div>
      <ul className="r-yaku">
        {win.yaku.map(([name, han], i) => (
          <li key={i}>
            <span>{name}</span>
            <span>{win.yakuman ? '役满' : `${han} 番`}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function HandResult({ view, onNext }: { view: RView; onNext: () => void }) {
  const r = view.result!
  const me = view.seat
  const title =
    r.type === 'win' ? `${roundName(r)} 和了` : `${roundName(r)} ${DRAW_REASONS[r.reason] ?? r.reason}`
  return (
    <div className="result-veil">
      <section className="result" role="dialog" aria-label="本局结算">
        <header>
          <h2>{title}</h2>
          {r.type === 'win' && (
            <p className="r-indicators">
              宝牌指示牌 <TilesInline tiles={r.dora_indicators ?? []} />
              {(r.ura_indicators ?? []).length > 0 && (
                <>
                  里宝指示牌 <TilesInline tiles={r.ura_indicators ?? []} />
                </>
              )}
            </p>
          )}
          {r.type === 'ryukyoku' && r.tenpai && (
            <p>听牌: {[0, 1, 2, 3].filter((s) => r.tenpai![s]).map((s) => whoIs(s, me)).join('、') || '没有人'}</p>
          )}
        </header>
        {(r.wins ?? []).map((w, i) => (
          <WinBlock key={i} win={w} me={me} />
        ))}
        <table className="result-table">
          <thead>
            <tr>
              <th scope="col">座位</th>
              <th scope="col">本局</th>
              <th scope="col">点数</th>
            </tr>
          </thead>
          <tbody>
            {[0, 1, 2, 3].map((s) => (
              <tr key={s} className={s === me ? 'is-me' : ''}>
                <th scope="row">
                  {whoIs(s, me)} <small>{seatWind(s, r.dealer)}</small>
                </th>
                <td className={r.deltas[s] > 0 ? 'up' : r.deltas[s] < 0 ? 'down' : ''}>{signed(r.deltas[s])}</td>
                <td>{r.scores[s]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="lobby-buttons">
          <button className="btn btn-primary" onClick={onNext}>
            下一局
          </button>
        </div>
      </section>
    </div>
  )
}

function FinalResult({ view, onAgain, onQuit }: { view: RView; onAgain: () => void; onQuit: () => void }) {
  const f = view.final!
  const me = view.seat
  const order = [0, 1, 2, 3].sort((a, b) => f.ranks[a] - f.ranks[b])
  const last = view.result
  return (
    <div className="result-veil">
      <section className="result" role="dialog" aria-label="终局">
        <header>
          <h2>你第 {f.ranks[me] + 1} 名</h2>
          <p>
            共 {f.hands} 局,{END_REASONS[f.end_reason] ?? f.end_reason}
          </p>
        </header>
        {last && last.type === 'win' && (last.wins ?? []).map((w, i) => <WinBlock key={i} win={w} me={me} />)}
        <table className="result-table">
          <thead>
            <tr>
              <th scope="col">名次</th>
              <th scope="col">座位</th>
              <th scope="col">点数</th>
              <th scope="col">名次分</th>
            </tr>
          </thead>
          <tbody>
            {order.map((s) => (
              <tr key={s} className={s === me ? 'is-me' : ''}>
                <td>{f.ranks[s] + 1}</td>
                <th scope="row">{whoIs(s, me)}</th>
                <td>{f.scores[s]}</td>
                <td className={f.final_points[s] > 0 ? 'up' : f.final_points[s] < 0 ? 'down' : ''}>
                  {signed(Math.round(f.final_points[s] * 10) / 10)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="r-note">名次分 = (点数 − 30000) ÷ 1000 + 顺位马(+20 / +10 / −10 / −20),第一名另加 20</p>
        <div className="lobby-buttons">
          <button className="btn btn-primary" onClick={onAgain}>
            再来一场
          </button>
          <button className="btn btn-ghost" onClick={onQuit}>
            回到开始页
          </button>
        </div>
      </section>
    </div>
  )
}

// ---------------------------------------------------------------- 侧栏

function RSidebar({
  match,
  view,
  log,
  connected,
  error,
  onQuit,
  onClose,
}: {
  match: RMatchInfo
  view: RView
  log: RLogged[]
  connected: boolean
  error: string | null
  onQuit: () => void
  onClose: () => void
}) {
  const me = view.seat
  const latest = log[log.length - 1]
  const ins = view.insight
  return (
    <aside className="side">
      <header className="side-head">
        <h2>{roundName({ ...view, honba: 0 })}</h2>
        <p>
          {view.honba}本场 · 供托 {view.sticks} · 对手{match.opponent_label}
        </p>
      </header>
      <table className="scores">
        <tbody>
          {[0, 1, 2, 3].map((s) => (
            <tr key={s} className={s === me ? 'is-me' : ''}>
              <th scope="row">
                {whoIs(s, me)} <small>{seatWind(s, view.dealer)}</small>
              </th>
              <td>{view.scores[s]}</td>
              <td>{view.riichi[s] ? '立直' : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ins && (
        <div className="advice">
          <p>
            {ins.discards ? `出牌后最好是${shantenText(ins.shanten)}` : shantenText(ins.shanten)}
            {ins.tiles && ins.total != null && `,${ins.shanten === 0 ? '听' : '进张'} ${ins.total} 张`}
          </p>
          {ins.tiles && ins.tiles.length > 0 && (
            <span className="r-inline r-wrap">
              {ins.tiles.map((x) => (
                <RTile key={x.tile} tile={x.tile} />
              ))}
            </span>
          )}
        </div>
      )}
      <div className="latest" aria-live="polite">
        {latest ? latest.text : '牌局开始'}
      </div>
      <details className="log-box">
        <summary>这一局的经过</summary>
        <ol className="log">
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
        <button className="btn btn-ghost" onClick={onQuit}>
          结束这一场
        </button>
        <button className="btn btn-ghost" onClick={onClose}>
          回到四川麻将
        </button>
      </footer>
    </aside>
  )
}

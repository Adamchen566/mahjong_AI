import { handInfoText, percent, RISKY, shantenText, Tile, TileCounts } from './Table'
import { tileName } from './tiles'
import type { Insight } from './types'

/** 侧栏里的牌理: 几向听、进哪些牌、听哪些牌。全是规则算出来的,只用这个座位看得到的牌。 */
export function InsightPanel({ info }: { info: Insight }) {
  return (
    <div className="tips">
      <span>牌理</span>
      {info.void_left > 0 && <p>手里还有 {info.void_left} 张缺门牌,要先打完才能听牌。</p>}
      {info.discards ? <Choices info={info} /> : <Thirteen info={info} />}
    </div>
  )
}

/** 轮到自己出牌: 说出最好的打法 */
function Choices({ info }: { info: Insight }) {
  const best = (info.discards ?? []).filter((o) => o.best)
  if (info.void_left > 0) return <p>打完之后最好能到{shantenText(info.shanten)}。</p>
  return (
    <>
      {best.slice(0, 2).map((o) => (
        <div key={o.tile} className="tips-row">
          <p>
            打 {tileName(o.tile)}: {handInfoText(o)}
          </p>
          <TileCounts items={o.waits ?? o.useful ?? []} />
        </div>
      ))}
      {best.length > 2 && <p>还有 {best.length - 2} 种打法一样好。</p>}
      <Risk info={info} />
      <p className="tips-note">手牌上的数字是打出那张之后的进张数,选中一张能看到细节。</p>
    </>
  )
}

/** 哪张最危险、哪张最稳。按和电脑打出来的牌局统计,不是对别人手牌的精确推断 */
function Risk({ info }: { info: Insight }) {
  const rated = (info.discards ?? []).filter((o) => o.danger)
  if (rated.length < 2) return null
  const sorted = [...rated].sort((a, b) => a.danger!.p - b.danger!.p)
  const safest = sorted[0]
  const worst = sorted[sorted.length - 1]
  return (
    <p className={worst.danger!.p >= RISKY ? 'is-risky' : ''}>
      点炮的可能: 最高是 {tileName(worst.tile)}({percent(worst.danger!.p)}),最低是 {tileName(safest.tile)}(
      {percent(safest.danger!.p)})
    </p>
  )
}

function Thirteen({ info }: { info: Insight }) {
  if (info.shanten > 0 || !info.waits) {
    return (
      <div className="tips-row">
        <p>{handInfoText({ shanten: info.shanten, total: info.total ?? 0, useful: info.useful })}</p>
        <TileCounts items={info.useful ?? []} />
      </div>
    )
  }
  if (!info.waits.length) return <p>听牌了,但要的牌已经没有了。</p>
  return (
    <>
      <p>听牌,一共还剩 {info.total} 张</p>
      <ul className="waits">
        {info.waits.map((w) => (
          <li key={w.tile} className={w.left === 0 ? 'is-gone' : ''}>
            <Tile tile={w.tile} size="xs" />
            <b>剩 {w.left} 张</b>
            <i>
              {w.fan} 番 {w.names.join(' ')}
            </i>
          </li>
        ))}
      </ul>
      <p className="tips-note">番数按点炮胡算,自摸另加。</p>
    </>
  )
}

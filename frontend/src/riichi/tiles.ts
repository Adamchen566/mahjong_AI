// 日麻的牌: 种类 0..33(万 0-8、筒 9-17、条 18-26、东南西北 27-30、白发中 31-33),
// 再加 34/35/36 = 赤 5 万/筒/条。和服务端 riichi/tiles.py 一致。
import type { REvent, RView } from './types'

export const WINDS = ['东', '南', '西', '北']
const SUIT_NAMES = ['万', '筒', '条']
const HONORS = ['东', '南', '西', '北', '白', '发', '中']
const SUIT_FILES = ['man', 'pin', 'sou']
const RELATIVE = ['你', '下家', '对家', '上家']

export const kindOf = (tile: number) => (tile >= 34 ? [4, 13, 22][tile - 34] : tile)
export const isRed = (tile: number) => tile >= 34

export function tileName(tile: number): string {
  if (tile >= 34) return `赤5${SUIT_NAMES[tile - 34]}`
  if (tile >= 27) return HONORS[tile - 27]
  return `${(tile % 9) + 1}${SUIT_NAMES[Math.floor(tile / 9)]}`
}

export function tileSrc(tile: number): string {
  if (tile >= 34) return `/tiles/${SUIT_FILES[tile - 34]}0.png`
  if (tile >= 31) return `/tiles/dragon${tile - 30}.png`
  if (tile >= 27) return `/tiles/wind${tile - 26}.png`
  return `/tiles/${SUIT_FILES[Math.floor(tile / 9)]}${(tile % 9) + 1}.png`
}

/** 手牌排序: 按种类,赤 5 排在普通 5 前面 */
export const sortKey = (tile: number) => (tile >= 34 ? kindOf(tile) - 0.5 : tile)

export const relativeOf = (seat: number, me: number) => (seat - me + 4) % 4
export const whoIs = (seat: number, me: number) => RELATIVE[relativeOf(seat, me)]
/** 座位的自风: 庄家是东 */
export const seatWind = (seat: number, dealer: number) => WINDS[(seat - dealer + 4) % 4]

export const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`)

export function roundName(view: Pick<RView, 'round_wind' | 'kyoku' | 'honba'>): string {
  return `${WINDS[view.round_wind % 4]}${view.kyoku + 1}局${view.honba ? ` ${view.honba}本场` : ''}`
}

export const DRAW_REASONS: Record<string, string> = {
  exhaustive: '荒牌流局',
  nagashi_mangan: '流局满贯',
  kyuushu: '九种九牌',
  suufon_renda: '四风连打',
  suukaikan: '四杠散了',
  suucha_riichi: '四家立直',
  sanchahou: '三家和',
}

export const END_REASONS: Record<string, string> = {
  finished: '南 4 局打完',
  dealer_top: '庄家第一,止和',
  tobi: '有人被击飞',
  overtime_target: '延长场里有人到 30000 点',
  overtime_over: '延长场打完',
}

const KAN_LABEL: Record<string, string> = { DAIMINKAN: '杠', ANKAN: '暗杠', KAKAN: '加杠' }

export interface RLogLine {
  text: string
  kind: 'info' | 'win' | 'mine'
}

/** 把一条事件写成牌局记录里的一行。返回 null 表示不值得记。 */
export function describeEvent(ev: REvent, me: number): RLogLine | null {
  const who = typeof ev.seat === 'number' ? whoIs(ev.seat, me) : ''
  const t = typeof ev.tile === 'number' ? tileName(ev.tile) : ''
  switch (ev.type) {
    case 'hand_start':
      return {
        text: `${roundName(ev as unknown as RView)},${whoIs(ev.dealer as number, me)}坐庄,宝牌指示牌 ${tileName(ev.dora_indicator as number)}`,
        kind: 'info',
      }
    case 'draw':
      return ev.seat === me && t ? { text: `你摸到 ${t}${ev.rinshan ? '(岭上牌)' : ''}`, kind: 'mine' } : null
    case 'discard':
      return { text: `${who}${ev.riichi ? '立直,' : ''}打出 ${t}`, kind: ev.seat === me ? 'mine' : 'info' }
    case 'riichi_accepted':
      return { text: `${who}${ev.double ? '双立直' : '立直'}成立`, kind: 'info' }
    case 'chi':
      return { text: `${who}吃 ${t}`, kind: 'info' }
    case 'pon':
      return { text: `${who}碰 ${t}`, kind: 'info' }
    case 'kan':
      return { text: `${who}${KAN_LABEL[ev.kind as string]} ${t}`, kind: 'info' }
    case 'kan_declared':
      return { text: `${who}要加杠 ${t}`, kind: 'info' }
    case 'dora':
      return { text: `新的宝牌指示牌 ${tileName(ev.indicator as number)}`, kind: 'info' }
    case 'hand_end': {
      const r = ev.result as { type: string; reason: string; wins?: { seat: number; tsumo: boolean; gain: number }[] }
      if (r.type === 'win' && r.wins) {
        return {
          text: r.wins.map((w) => `${whoIs(w.seat, me)}${w.tsumo ? '自摸' : '荣和'} +${w.gain}`).join(','),
          kind: 'win',
        }
      }
      return { text: DRAW_REASONS[r.reason] ?? r.reason, kind: 'info' }
    }
    case 'game_end':
      return { text: '整场结束', kind: 'info' }
    default:
      return null
  }
}

/** 需要在座位旁边喊出来的事件。 */
export function calloutOf(ev: REvent): { seat: number; text: string } | null {
  if (typeof ev.seat !== 'number') {
    if (ev.type === 'hand_end') {
      const r = ev.result as { type: string; wins?: { seat: number; tsumo: boolean }[] }
      const w = r.wins?.[0]
      if (r.type === 'win' && w) return { seat: w.seat, text: w.tsumo ? '自摸' : '荣和' }
    }
    return null
  }
  if (ev.type === 'riichi') return { seat: ev.seat, text: '立直' }
  if (ev.type === 'chi') return { seat: ev.seat, text: '吃' }
  if (ev.type === 'pon') return { seat: ev.seat, text: '碰' }
  if (ev.type === 'kan') return { seat: ev.seat, text: '杠' }
  return null
}

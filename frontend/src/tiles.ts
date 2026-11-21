import type { GameEvent, View } from './types'

export const SUIT_NAMES = ['万', '筒', '条']
export const WINDS = ['东', '南', '西', '北']
const SUIT_FILES = ['man', 'pin', 'sou']
const RELATIVE = ['你', '下家', '对家', '上家']
const DIRECTIONS: Record<number, string> = { 1: '下家', 2: '对家', 3: '上家' }

export const suitOf = (tile: number) => Math.floor(tile / 9)
export const rankOf = (tile: number) => (tile % 9) + 1
export const tileName = (tile: number) => `${rankOf(tile)}${SUIT_NAMES[suitOf(tile)]}`
export const tileSrc = (tile: number) => `/tiles/${SUIT_FILES[suitOf(tile)]}${rankOf(tile)}.png`

/** 座位相对于玩家的位置: 0 自己(下) 1 下家(右) 2 对家(上) 3 上家(左) */
export const relativeOf = (seat: number, me: number) => (seat - me + 4) % 4
export const whoIs = (seat: number, me: number) => RELATIVE[relativeOf(seat, me)]

export const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`)

const GANG_LABEL: Record<string, string> = { AN_GANG: '暗杠', JIA_GANG: '加杠', MING_GANG: '杠' }
const TRANSFER_LABEL: Record<string, string> = {
  hu: '胡牌',
  gang: '杠分',
  hua_zhu: '查花猪',
  da_jiao: '查大叫',
  tui_shui: '退税',
}

export interface LogLine {
  text: string
  kind: 'info' | 'win' | 'money' | 'mine'
}

/** 把一条事件写成牌局记录里的一行。返回 null 表示不值得记。 */
export function describeEvent(ev: GameEvent, me: number, view: View | null): LogLine | null {
  const who = typeof ev.seat === 'number' ? whoIs(ev.seat, me) : ''
  switch (ev.type) {
    case 'deal':
      return { text: `发牌,${whoIs(ev.dealer, me)}坐庄`, kind: 'info' }
    case 'exchange': {
      const got = view?.exchange.received ?? []
      const tail = got.length ? `,你收到 ${got.map(tileName).join(' ')}` : ''
      return { text: `换三张,牌给了${DIRECTIONS[ev.direction]}${tail}`, kind: 'info' }
    }
    case 'void':
      return {
        text: '定缺: ' + (ev.voids as number[]).map((v, s) => `${whoIs(s, me)}缺${SUIT_NAMES[v]}`).join(',') ,
        kind: 'info',
      }
    case 'draw':
      if (ev.seat !== me || ev.tile == null) return null
      return { text: `你摸到 ${tileName(ev.tile)}${ev.after_gang ? '(杠后补牌)' : ''}`, kind: 'mine' }
    case 'discard':
      return { text: `${who}打出 ${tileName(ev.tile)}`, kind: ev.seat === me ? 'mine' : 'info' }
    case 'pong':
      return { text: `${who}碰 ${tileName(ev.tile)}`, kind: 'info' }
    case 'gang_declared':
      return { text: `${who}要加杠 ${tileName(ev.tile)}`, kind: 'info' }
    case 'gang':
      return { text: `${who}${GANG_LABEL[ev.kind]}${ev.tile == null ? '' : ' ' + tileName(ev.tile)}`, kind: 'info' }
    case 'hu': {
      const tile = ev.tile == null ? '' : ` ${tileName(ev.tile)}`
      const how = ev.zimo ? `自摸${tile}` : `胡了${whoIs(ev.from_seat, me)}的${tile.trim()}`
      return { text: `${who}${how},${ev.names.join(' ')},${ev.fan} 番`, kind: 'win' }
    }
    case 'transfer':
      return {
        text: `${whoIs(ev.payer, me)}付给${whoIs(ev.payee, me)} ${ev.amount} 分(${TRANSFER_LABEL[ev.kind] ?? ev.kind})`,
        kind: 'money',
      }
    case 'end':
      return { text: ev.reason === 'three_won' ? '三家已胡,本局结束' : '牌墙摸完,本局结束', kind: 'info' }
    default:
      return null
  }
}

/** 需要在座位旁边喊出来的事件。 */
export function calloutOf(ev: GameEvent): { seat: number; text: string } | null {
  if (ev.type === 'hu') return { seat: ev.seat, text: ev.zimo ? '自摸' : '胡' }
  if (ev.type === 'pong') return { seat: ev.seat, text: '碰' }
  if (ev.type === 'gang') return { seat: ev.seat, text: '杠' }
  return null
}

export const transferLabel = (kind: string) => TRANSFER_LABEL[kind] ?? kind

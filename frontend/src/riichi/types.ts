// 日麻服务端(/ws/riichi)发来的数据结构,字段含义见 docs/riichi-rules.md 和 server/riichi_match.py

export type RPhase = 'TURN' | 'RIICHI' | 'RESPONSE' | 'ROB_KAN' | 'END'

export type RActionType =
  | 'DISCARD'
  | 'ANKAN'
  | 'KAKAN'
  | 'RIICHI'
  | 'CHI'
  | 'PON'
  | 'DAIMINKAN'
  | 'TSUMO'
  | 'RON'
  | 'KYUUSHU'
  | 'PASS'

export interface RLegal {
  id: number
  type: RActionType
  tile: number
  text: string
  /** 吃碰: 从手里拿出去的两张牌 */
  uses?: number[]
}

export interface RMeld {
  type: 'CHI' | 'PON' | 'DAIMINKAN' | 'ANKAN' | 'KAKAN'
  tiles: number[]
  called: number
  from_seat: number
}

export interface RWin {
  seat: number
  from_seat: number
  tsumo: boolean
  tile: number
  han: number
  fu: number
  yaku: [string, number][]
  yakuman: number
  limit: string
  gain: number
  hand: number[]
  melds: RMeld[]
  riichi: number
}

export interface RHandResult {
  type: 'win' | 'ryukyoku' | 'test'
  reason: string
  wins?: RWin[]
  dora_indicators?: number[]
  ura_indicators?: number[]
  tenpai?: boolean[] | null
  nagashi?: number[]
  hands?: (number[] | null)[]
  round_wind: number
  kyoku: number
  honba: number
  dealer: number
  deltas: number[]
  scores: number[]
  renchan: boolean
}

export interface RTileLeft {
  tile: number
  left: number
}

export interface RHandInfo {
  shanten: number
  tiles: RTileLeft[]
  total: number
  best?: boolean
}

export interface RInsight {
  shanten: number
  tiles?: RTileLeft[]
  total?: number
  /** 轮到自己出牌时: 打出每一种(保持最小向听的)牌之后的进张 */
  discards?: Record<string, RHandInfo>
}

export interface RView {
  seat: number
  phase: RPhase
  current: number
  round_wind: number
  kyoku: number
  honba: number
  sticks: number
  dealer: number
  seat_wind: number
  scores: number[]
  wall_remaining: number
  dora_indicators: number[]
  hand: number[]
  drawn: number | null
  hand_sizes: number[]
  melds: RMeld[][]
  discards: number[][]
  /** 每张弃牌: [是否摸切, 是否立直宣言牌, 是否被吃碰杠走] */
  discard_flags: [boolean, boolean, boolean][][]
  riichi: number[]
  riichi_pending: number
  ippatsu: boolean[]
  furiten: boolean
  pending: { seat: number; tile: number; kind: 'discard' | 'kakan' | 'ankan' } | null
  kuikae: number[]
  legal: RLegal[]
  insight?: RInsight
  result?: RHandResult | null
  final?: { scores: number[]; ranks: number[]; final_points: number[]; end_reason: string; hands: number }
  record?: string | null
}

export interface RMatchInfo {
  opponent: string
  opponent_label: string
  human_seat: number
  paused: boolean
  over: boolean
}

export interface REvent {
  type: string
  seat?: number
  tile?: number | null
  [key: string]: unknown
}

export interface RStateMessage {
  type: 'state'
  match: RMatchInfo | null
  view: RView | null
  events: REvent[]
}

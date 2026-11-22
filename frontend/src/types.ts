// 服务端发来的数据结构,字段含义见 docs/architecture.md

export type MeldType = 'PONG' | 'MING_GANG' | 'AN_GANG' | 'JIA_GANG'

export interface Meld {
  type: MeldType
  tile: number | null // 别人的暗杠看不到牌
  from_seat: number
}

export interface Win {
  seat: number
  tile: number | null
  zimo: boolean
  from_seat: number | null
  fan: number
  points: number
  names: string[]
}

export interface Legal {
  id: number
  type: 'DISCARD' | 'AN_GANG' | 'JIA_GANG' | 'PONG' | 'MING_GANG' | 'HU' | 'PASS' | 'CHOOSE_VOID' | 'EXCHANGE'
  tile: number
}

/** 模型的建议: 概率最高的几个动作,和它估计这一局还会得多少分 */
export interface Hint {
  value: number
  choices: (Legal & { prob: number; text: string })[]
  tiles: TileProb[] // 每一张能打(或能换)的牌的概率,画概率条用
}

/** [牌, 概率] */
export type TileProb = [number, number]

/** 一种牌,和这个座位还没见过的张数 */
export interface TileLeft {
  tile: number
  left: number
}

/** 听的一张牌: 还剩几张、点炮胡几番 */
export interface Wait extends TileLeft {
  fan: number
  points: number
  names: string[]
}

/** 打出一张牌点炮的可能: p 是至少被一家胡的概率,by 是 [座位, 概率],只列可能胡它的那几家 */
export interface Danger {
  p: number
  by: [number, number][]
}

/** 13 张时的牌理: 几向听;没听牌时有进张(useful),听牌时有能胡的牌(waits) */
export interface HandInfo {
  shanten: number
  total: number
  useful?: TileLeft[]
  waits?: Wait[]
}

/** 这个座位现在的牌理。轮到自己出牌时没有 useful/waits,而是每一张能打的牌各一份(discards) */
export interface Insight extends Partial<HandInfo> {
  shanten: number
  void_left: number
  discards?: (HandInfo & { tile: number; best: boolean; danger?: Danger })[]
}

export interface Transfer {
  kind: 'hu' | 'gang' | 'hua_zhu' | 'da_jiao' | 'tui_shui'
  payer: number
  payee: number
  amount: number
  note: string
}

export type Phase = 'EXCHANGE' | 'CHOOSE_VOID' | 'TURN' | 'RESPONSE' | 'ROB_KONG' | 'END'

export interface View {
  seat: number
  phase: Phase
  current: number
  dealer: number
  wall_remaining: number
  hand: number[]
  drawn: number | null
  hand_sizes: number[]
  melds: Meld[][]
  discards: number[][]
  void: (number | null)[]
  won: boolean[]
  wins: Win[]
  scores: number[]
  pending_discard: { seat: number; tile: number; rob_kong?: boolean } | null
  exchange: { given: number[]; received: number[]; direction: number | null }
  legal: Legal[]
  hint?: Hint // 打开提示、并且轮到你时才有
  insight?: Insight // 向听数、进张、听牌: 打牌阶段、还没胡时才有
  hands?: number[][] // 牌局结束或回放时才有
  shanten?: (number | null)[] // 回放时才有: 四家各自的向听数
  seat_labels?: string[] // 观战时才有: 四个座位各是哪种电脑
  end_reason?: 'three_won' | 'wall_exhausted'
  transfers?: Transfer[]
  record?: string | null
}

export interface MatchInfo {
  game_no: number
  totals: number[]
  opponent: string
  opponent_label: string
  human_seat: number
  seat_names: string[]
  hint_available: boolean // 有没有可用的模型
  hint_on: boolean
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type GameEvent = { type: string } & Record<string, any>

export interface StateMessage {
  type: 'state'
  match: MatchInfo | null
  view: View | null
  events: GameEvent[]
}

/** 回放时模型对每一步的看法。steps[i] 对应牌谱的第 i+1 步 */
export interface AnalysisStep {
  seat: number
  forced: boolean
  value: number // 模型估计这一家这一局还会得多少分
  score: number // 这一家当时已经得的分
  agree?: boolean
  best?: Legal & { prob: number; text: string }
  chosen?: Legal & { prob: number; text: string }
  top?: (Legal & { prob: number; text: string })[]
  tiles?: TileProb[]
}

export interface Analysis {
  available: boolean
  reason?: string
  steps?: AnalysisStep[]
  summary?: { seat: number; decisions: number; agreed: number }[]
  final?: number[]
}

/** 牌谱里的一步 */
export interface RecordStep {
  seat: number
  text: string
  type: Legal['type']
  tile: number
  zimo: boolean
}

/** 段位梯: 各个版本两两对打的成绩,和训练过程中的评估曲线 */
export interface Ladder {
  available: boolean
  reason?: string
  generated_at?: string
  games_per_pair?: number
  players?: { id: string; label: string; note: string; games?: number | null }[]
  /** matrix[i][j]: 第 i 个版本和三个第 j 个版本同桌时,平均每局得分和 95% 区间 */
  matrix?: ({ mean: number; lo: number; hi: number; win_rate: number; deal_in_rate: number } | null)[][]
  curve?: { games: number; score: number; lo: number; hi: number; deal_in_rate: number }[]
}

export interface RecordSummary {
  name: string
  saved_at: string | null
  game_no: number | null
  opponent: string | null
  human_seat: number
  steps: number
  scores: number[] | null
}

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
  hands?: number[][] // 牌局结束或回放时才有
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
  agree?: boolean
  best?: Legal & { prob: number; text: string }
  chosen?: Legal & { prob: number; text: string }
  value?: number
}

export interface Analysis {
  available: boolean
  reason?: string
  steps?: AnalysisStep[]
  summary?: { seat: number; decisions: number; agreed: number }[]
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

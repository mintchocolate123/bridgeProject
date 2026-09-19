// 平台 API 回傳的資料格式。對應 bridge-platform/docs/api-design.md。

export type Seat = 'N' | 'E' | 'S' | 'W'
export type Strain = 'C' | 'D' | 'H' | 'S' | 'N'
export type Vulnerability = 'none' | 'NS' | 'EW' | 'both'
export type RoomStatus = 'waiting' | 'playing' | 'finished' | 'aborted' | 'expired'
export type Phase = 'bidding' | 'playing' | 'finished'

export const SEATS: Seat[] = ['N', 'E', 'S', 'W']

export interface Contract {
  level: number
  strain: Strain
  declarer: Seat
  doubled: 'none' | 'doubled' | 'redoubled'
}

export interface Call {
  seat: Seat
  bid: string
}

export interface PlayedCard {
  seat: Seat
  card: string
}

export interface Trick {
  number: number
  leader: Seat
  cards: PlayedCard[]
  winner: Seat
}

export interface DealResult {
  contract: Contract | null
  passed_out: boolean
  declarer: Seat | null
  tricks: number | null
  score: number
  ns_score: number
}

export interface BoardResult extends DealResult {
  board: number
}

// bridge-core Deal.view() 的內容。看不到的手牌是 null
export interface DealView {
  board_id: string | null
  viewer: string
  dealer: Seat
  vulnerability: Vulnerability
  phase: Phase
  hands: Record<Seat, string[] | null>
  hand_counts: Record<Seat, number>
  auction: Call[]
  contract: Contract | null
  passed_out: boolean
  declarer: Seat | null
  dummy: Seat | null
  dummy_revealed: boolean
  turn: { seat: Seat; actor: Seat; phase: 'bid' | 'play' } | null
  current_trick: PlayedCard[]
  tricks: Trick[]
  counts: { NS: number; EW: number }
  result: DealResult | null
}

export interface RoomSummary {
  room_code: string
  status: RoomStatus
  seats: Record<Seat, string | null>
  boards: number
  board: number | null
  board_index: number
  created_by: string
  created_at: string
  ended_reason: string | null
  ended_by_seat: Seat | null
}

export interface PublicTurn {
  turn_id: string
  board: number
  seat: Seat
  actor: Seat
  phase: 'bid' | 'play'
  deadline: string
}

export interface RoomState extends RoomSummary {
  last_seq: number
  viewer: string
  view: DealView | null
  turn: PublicTurn | null
  results: BoardResult[]
}

export interface ReplayFrame {
  step: number
  action: { seat: Seat; actor: Seat; phase: 'bid' | 'play'; action: string } | null
  view: DealView
}

export interface Replay {
  room_code: string
  index: number
  total: number
  board: number
  incomplete: boolean
  frames: ReplayFrame[]
}

export interface RoomRecord extends RoomSummary {
  players: Record<Seat, { name: string; total_timeouts: number } | null>
  deals: { board_id: string | null; incomplete?: boolean }[]
  results: BoardResult[]
}

// 串流事件。只列出前端會用到的欄位
export interface PlatformEvent {
  seq?: number
  type: string
  [key: string]: unknown
}

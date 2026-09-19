// 把平台的標準記號轉成畫面上的文字。規則判斷一律交給平台,這裡只管顯示。

import type { Contract, Seat, Strain, Vulnerability } from './api/types'

export const SUIT_SYMBOL: Record<string, string> = { S: '♠', H: '♥', D: '♦', C: '♣' }
export const SUIT_ORDER = ['S', 'H', 'D', 'C']
const RANK_ORDER = 'AKQJT98765432'

export function isRed(suit: string): boolean {
  return suit === 'H' || suit === 'D'
}

/** "HT" -> { suit: "H", rank: "10" } */
export function parseCard(card: string): { suit: string; rank: string } {
  const suit = card[0]
  const rank = card.slice(1)
  return { suit, rank: rank === 'T' ? '10' : rank }
}

/** 依 ♠♥♦♣、大到小排序。平台已經排好,這裡是保險 */
export function sortCards(cards: string[]): string[] {
  return [...cards].sort(
    (a, b) =>
      SUIT_ORDER.indexOf(a[0]) - SUIT_ORDER.indexOf(b[0]) || RANK_ORDER.indexOf(a[1]) - RANK_ORDER.indexOf(b[1]),
  )
}

export function strainText(strain: Strain | string): string {
  return strain === 'N' ? 'NT' : SUIT_SYMBOL[strain] ?? strain
}

/** 叫品拆成數字與花色,方便把紅色花色上色。P / X / XX 回傳 kind */
export function parseCall(call: string): { kind: 'bid' | 'pass' | 'double' | 'redouble'; level?: string; strain?: string } {
  if (call === 'P') return { kind: 'pass' }
  if (call === 'X') return { kind: 'double' }
  if (call === 'XX') return { kind: 'redouble' }
  return { kind: 'bid', level: call[0], strain: call.slice(1) }
}

export function contractText(c: Contract | null, passedOut = false, passText = 'Pass'): string {
  if (passedOut || !c) return passText
  const dbl = c.doubled === 'doubled' ? 'X' : c.doubled === 'redoubled' ? 'XX' : ''
  return `${c.level}${strainText(c.strain)}${dbl}`
}

export function isVulnerable(seat: Seat, vul: Vulnerability): boolean {
  if (vul === 'both') return true
  if (vul === 'none') return false
  return vul.includes(seat)
}

export function partnerOf(seat: Seat): Seat {
  return ({ N: 'S', S: 'N', E: 'W', W: 'E' } as const)[seat]
}

/** 莊家方的墩數寫成 +1 / =  / -2 */
export function overUnder(level: number, tricks: number): string {
  const diff = tricks - (level + 6)
  return diff === 0 ? '=' : diff > 0 ? `+${diff}` : String(diff)
}

export function signed(n: number): string {
  return n > 0 ? `+${n}` : String(n)
}

export function formatTime(iso: string, locale: string): string {
  const d = new Date(iso)
  return d.toLocaleString(locale === 'zh' ? 'zh-TW' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

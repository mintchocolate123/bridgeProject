// 把平台事件與結束原因轉成一句話,給事件紀錄與提示用
import { useI18n } from './i18n'
import { contractText, signed } from './format'
import type { Contract, PlatformEvent, RoomSummary, Seat } from './api/types'

export function useDescribe() {
  const { t } = useI18n()
  const seat = (s: unknown) => t(`seat.${String(s)}`)

  function endReason(room: Pick<RoomSummary, 'status' | 'ended_reason' | 'ended_by_seat'>): string {
    if (room.status === 'finished') return t('end.finished')
    if (room.status === 'expired') return t('end.expired')
    if (room.ended_reason === 'timeout' && room.ended_by_seat) return t('end.timeout', { seat: seat(room.ended_by_seat) })
    return t('end.aborted', { reason: room.ended_reason ?? '' })
  }

  function event(e: PlatformEvent): string {
    switch (e.type) {
      case 'room_update': {
        if (e.status === 'playing') return t('log.started')
        const seats = e.seats as Record<Seat, string | null>
        return t('log.seated', { n: Object.values(seats).filter(Boolean).length })
      }
      case 'board_start':
        return t('log.boardStart', { board: e.board as number, index: e.index as number, total: e.total as number })
      case 'auction_end':
        return e.passed_out
          ? t('log.passedOut', { board: e.board as number })
          : t('log.contract', {
              contract: contractText(e.contract as Contract),
              seat: seat(e.declarer),
            })
      case 'board_end':
        return t('log.boardEnd', { board: e.board as number, score: signed(e.ns_score as number) })
      case 'timeout':
        return t('log.timeout', { seat: seat(e.seat), n: e.consecutive as number })
      case 'room_end':
        return endReason({
          status: e.status as RoomSummary['status'],
          ended_reason: (e.reason as string) ?? null,
          ended_by_seat: (e.seat as Seat) ?? null,
        })
      default:
        return e.type
    }
  }

  return { endReason, event }
}

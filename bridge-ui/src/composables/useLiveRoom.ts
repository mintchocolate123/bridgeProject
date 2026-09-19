// 即時追蹤一個房間:先抓一次狀態,再接事件串流,每收到事件就重新抓狀態。
//
// 畫面完全以平台給的狀態為準,前端不自己推算牌局,所以不需要懂橋牌規則,
// 也不會和平台算出不一樣的結果。事件太密集時會合併成一次請求。

import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { ApiError, api, openStream, type StreamStatus } from '../api/client'
import type { PlatformEvent, RoomState } from '../api/types'

const LOGGED = new Set(['room_update', 'board_start', 'auction_end', 'board_end', 'timeout', 'room_end'])
const LOG_LIMIT = 40

export function useLiveRoom(code: Ref<string>, adminKey?: Ref<string>) {
  const room = ref<RoomState | null>(null)
  const error = ref<ApiError | null>(null)
  const streamStatus = ref<StreamStatus>('connecting')
  const log = ref<PlatformEvent[]>([])
  const now = ref(Date.now())

  let closeStream: (() => void) | null = null
  let loading = false
  let dirty = false

  const isAdmin = computed(() => !!adminKey?.value)

  async function load() {
    if (loading) {
      dirty = true
      return
    }
    loading = true
    try {
      do {
        dirty = false
        room.value = isAdmin.value
          ? await api.admin.room(adminKey!.value, code.value)
          : await api.room(code.value)
        error.value = null
      } while (dirty)
    } catch (e) {
      error.value = e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e))
    } finally {
      loading = false
    }
  }

  function start() {
    stop()
    log.value = []
    room.value = null
    load()
    const path = isAdmin.value
      ? `/admin/rooms/${encodeURIComponent(code.value)}/stream`
      : `/rooms/${encodeURIComponent(code.value)}/spectate`
    closeStream = openStream(path, {
      key: adminKey?.value,
      onEvent(event) {
        if (LOGGED.has(event.type)) {
          log.value = [event, ...log.value].slice(0, LOG_LIMIT)
        }
        load()
      },
      onStatus(status, err) {
        streamStatus.value = status
        if (err && status === 'closed') error.value = err
        if (status === 'open' || status === 'ended') load() // 重連後補上漏掉的變化
      },
    })
  }

  function stop() {
    closeStream?.()
    closeStream = null
  }

  const timer = window.setInterval(() => (now.value = Date.now()), 1000)

  // 剩餘秒數。平台的 deadline 是含時區的 ISO 字串
  const secondsLeft = computed(() => {
    const deadline = room.value?.turn?.deadline
    if (!deadline) return null
    return Math.max(0, Math.round((new Date(deadline).getTime() - now.value) / 1000))
  })

  watch([code, () => adminKey?.value], start, { immediate: true })
  onBeforeUnmount(() => {
    stop()
    window.clearInterval(timer)
  })

  return { room, error, streamStatus, log, secondsLeft, reload: load }
}

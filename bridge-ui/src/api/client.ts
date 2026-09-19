// 與平台溝通。前端只呼叫觀戰用的公開端點,以及主辦方端點(需要 admin key)。
// 玩家端點(token、/state、/action)留給之後的真人對局頁面。

import type { PlatformEvent, Replay, RoomRecord, RoomState, RoomSummary } from './types'

const BASE = '/api/v1'

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

async function request<T>(method: string, path: string, opts: { body?: unknown; key?: string } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.key) headers['Authorization'] = `Bearer ${opts.key}`
  let res: Response
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'network_error', 'cannot reach the platform')
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const err = data?.error ?? {}
    throw new ApiError(res.status, err.code ?? 'http_error', err.message ?? res.statusText)
  }
  return data as T
}

export const api = {
  rooms: (status?: string) => request<RoomSummary[]>('GET', '/rooms' + (status ? `?status=${status}` : '')),
  room: (code: string) => request<RoomState>('GET', `/rooms/${encodeURIComponent(code)}`),
  record: (code: string) => request<RoomRecord>('GET', `/rooms/${encodeURIComponent(code)}/record`),
  replay: (code: string, index: number) =>
    request<Replay>('GET', `/rooms/${encodeURIComponent(code)}/replay/${index}`),

  admin: {
    room: (key: string, code: string) =>
      request<RoomState>('GET', `/admin/rooms/${encodeURIComponent(code)}`, { key }),
    create: (key: string, body: unknown) => request<RoomSummary>('POST', '/admin/rooms', { key, body }),
    abort: (key: string, code: string, reason?: string) =>
      request<RoomSummary>('POST', `/admin/rooms/${encodeURIComponent(code)}/abort`, {
        key,
        body: reason ? { reason } : {},
      }),
  },
}

export type StreamStatus = 'connecting' | 'open' | 'retrying' | 'ended' | 'closed'

export interface StreamOptions {
  key?: string
  onEvent: (event: PlatformEvent) => void
  onStatus?: (status: StreamStatus, error?: ApiError) => void
}

/**
 * 讀取平台的事件串流(SSE)。
 *
 * 不用瀏覽器的 EventSource,因為它不能帶 Authorization 標頭,主辦方串流需要。
 * 斷線會自動重連,並用 Last-Event-ID 從斷掉的地方接著讀,不會漏事件。
 * 回傳一個函式,呼叫它就關閉串流。
 */
export function openStream(path: string, opts: StreamOptions): () => void {
  const controller = new AbortController()
  let lastId: number | null = null
  let closed = false

  const status = (s: StreamStatus, e?: ApiError) => opts.onStatus?.(s, e)

  async function connectOnce(): Promise<'ended' | 'retry' | 'fatal'> {
    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    if (opts.key) headers['Authorization'] = `Bearer ${opts.key}`
    if (lastId !== null) headers['Last-Event-ID'] = String(lastId)

    const res = await fetch(BASE + path, { headers, signal: controller.signal })
    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => null)
      const err = new ApiError(res.status, data?.error?.code ?? 'http_error', data?.error?.message ?? '')
      // 401/403/404 重試也沒用;429 與 5xx 等一下再試
      if ([401, 403, 404].includes(res.status)) {
        status('closed', err)
        return 'fatal'
      }
      status('retrying', err)
      return 'retry'
    }

    status('open')
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) return 'retry'
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let cut: number
      while ((cut = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, cut)
        buffer = buffer.slice(cut + 2)
        const data: string[] = []
        let id: number | null = null
        for (const line of block.split('\n')) {
          if (line.startsWith('data:')) data.push(line.slice(5).trim())
          else if (line.startsWith('id:')) id = Number(line.slice(3).trim())
        }
        if (!data.length) continue // keep-alive 註解
        const event = JSON.parse(data.join('\n')) as PlatformEvent
        if (id !== null && !Number.isNaN(id)) lastId = id
        if (event.type === 'stream_end') {
          status('ended')
          return 'ended'
        }
        opts.onEvent(event)
      }
    }
  }

  ;(async () => {
    status('connecting')
    while (!closed) {
      let outcome: 'ended' | 'retry' | 'fatal'
      try {
        outcome = await connectOnce()
      } catch {
        if (closed) return
        status('retrying')
        outcome = 'retry'
      }
      if (outcome !== 'retry') return
      await new Promise((r) => setTimeout(r, 2000))
    }
  })()

  return () => {
    closed = true
    controller.abort()
  }
}

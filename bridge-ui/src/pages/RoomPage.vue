<script setup lang="ts">
// 即時牌桌。觀眾只看得到明手;主辦方模式(admin)四家全開,需要金鑰。
import { computed, toRef } from 'vue'
import { RouterLink } from 'vue-router'
import BridgeTable from '../components/BridgeTable.vue'
import AuctionTable from '../components/AuctionTable.vue'
import ResultsTable from '../components/ResultsTable.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useLiveRoom } from '../composables/useLiveRoom'
import { useAdminKey } from '../composables/useAdminKey'
import { useI18n } from '../i18n'
import { useDescribe } from '../describe'
import { SEATS } from '../api/types'

const props = defineProps<{ code: string; admin?: boolean }>()
const { t } = useI18n()
const describe = useDescribe()

const storedKey = useAdminKey()
const adminKey = computed(() => (props.admin ? storedKey.value : ''))
const code = toRef(props, 'code')
const { room, error, streamStatus, log, secondsLeft } = useLiveRoom(code, adminKey)

const ended = computed(() => !!room.value && ['finished', 'aborted', 'expired'].includes(room.value.status))
const seated = computed(() => (room.value ? SEATS.filter((s) => room.value!.seats[s]).length : 0))

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
function time(iso: unknown): string {
  return typeof iso === 'string' ? new Date(iso).toLocaleTimeString() : ''
}
</script>

<template>
  <div class="page">
    <div v-if="admin && !storedKey" class="notice">
      {{ t('admin.needKey') }} <RouterLink to="/admin">{{ t('nav.admin') }}</RouterLink>
    </div>

    <div v-else-if="error && !room" class="notice error">
      <template v-if="error.code === 'room_not_found'">{{ t('room.notFound', { code }) }}</template>
      <template v-else-if="error.code === 'invalid_admin_key'">{{ t('admin.badKey') }}</template>
      <template v-else-if="error.code === 'network_error'">{{ t('error.network') }}</template>
      <template v-else>{{ error.message || error.code }}</template>
      <RouterLink to="/">{{ t('nav.back') }}</RouterLink>
    </div>

    <div v-else-if="!room" class="notice">{{ t('common.loading') }}</div>

    <template v-else>
      <header class="bar">
        <h1>
          {{ t('room.title', { code: room.room_code }) }}
          <StatusBadge :status="room.status" />
          <span v-if="admin" class="admin-tag">{{ t('admin.allVisible') }}</span>
        </h1>
        <div class="facts">
          <span v-if="room.board">{{ t('room.board', { n: room.board, index: room.board_index, total: room.boards }) }}</span>
          <span v-if="room.turn">
            {{ t('room.turn', { seat: t(`seat.${room.turn.seat}`), phase: t(`phase.${room.turn.phase}`) }) }}
            <span v-if="room.turn.actor !== room.turn.seat">({{ t('room.byDeclarer', { seat: t(`seat.${room.turn.actor}`) }) }})</span>
            <span v-if="secondsLeft !== null" class="clock" :class="{ low: secondsLeft < 60 }">{{ clock(secondsLeft) }}</span>
          </span>
          <span class="live" :class="streamStatus">{{ t(`stream.${streamStatus}`) }}</span>
        </div>
      </header>

      <div v-if="ended" class="notice ended">
        {{ describe.endReason(room) }}
        <RouterLink v-if="room.status !== 'expired'" :to="`/rooms/${room.room_code}/replay`">{{ t('room.toReplay') }}</RouterLink>
      </div>

      <div v-if="room.status === 'waiting'" class="waiting">
        <p>{{ t('room.waiting', { n: seated }) }}</p>
        <ul>
          <li v-for="s in SEATS" :key="s">
            <strong>{{ t(`seat.${s}`) }}</strong> {{ room.seats[s] ?? t('room.empty') }}
          </li>
        </ul>
        <p class="hint">{{ t('room.joinHint', { code: room.room_code }) }}</p>
      </div>

      <div v-else class="layout">
        <div class="main">
          <BridgeTable v-if="room.view" :view="room.view" :names="room.seats" />
          <p v-if="!admin && room.status === 'playing'" class="hint">{{ t('room.publicHint') }}</p>
        </div>

        <aside class="side">
          <section v-if="room.view" class="panel">
            <h2>{{ t('table.auction') }}</h2>
            <AuctionTable
              :auction="room.view.auction"
              :dealer="room.view.dealer"
              :vulnerability="room.view.vulnerability"
              :waiting="room.view.phase === 'bidding' && room.status === 'playing'"
            />
          </section>

          <section class="panel">
            <h2>{{ t('result.title') }}</h2>
            <ResultsTable :results="room.results" :current="room.board" />
          </section>

          <section class="panel">
            <h2>{{ t('log.title') }}</h2>
            <ol class="log">
              <li v-for="e in log" :key="e.seq" :class="{ warn: e.type === 'timeout' }">
                <time>{{ time(e.ts) }}</time> {{ describe.event(e) }}
              </li>
              <li v-if="!log.length" class="muted">—</li>
            </ol>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px 16px;
  margin-bottom: 12px;
}
h1 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 1.3rem;
}
.admin-tag {
  font-size: 0.75rem;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--danger-soft);
  color: var(--danger);
}
.facts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  font-size: 0.9rem;
  color: var(--muted);
}
.clock {
  margin-left: 6px;
  font-variant-numeric: tabular-nums;
  color: var(--text);
  font-weight: 600;
}
.clock.low {
  color: var(--danger);
}
.live::before {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 5px;
  border-radius: 50%;
  background: var(--muted);
}
.live.open::before {
  background: #2fb36b;
}
.live.retrying::before {
  background: #e0a526;
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}
.side {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.panel {
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.panel h2 {
  margin: 0 0 8px;
  font-size: 0.9rem;
  color: var(--muted);
}
.log {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
  font-size: 0.82rem;
}
.log li {
  padding: 2px 0;
}
.log time {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  margin-right: 4px;
}
.log .warn {
  color: var(--danger);
}
.waiting {
  padding: 24px;
  border-radius: 12px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.waiting ul {
  list-style: none;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}
.hint {
  font-size: 0.82rem;
  color: var(--muted);
}
.notice.ended {
  margin-bottom: 12px;
}
.notice a {
  margin-left: 8px;
}
@media (max-width: 1100px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>

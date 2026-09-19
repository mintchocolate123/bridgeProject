<script setup lang="ts">
// 大廳:房間列表,每 3 秒更新。也可以直接輸入房號。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, api } from '../api/client'
import { useI18n } from '../i18n'
import { formatTime } from '../format'
import { SEATS, type RoomSummary } from '../api/types'

const { t, locale } = useI18n()
const router = useRouter()

const FILTERS = ['all', 'playing', 'waiting', 'finished'] as const
const filter = ref<(typeof FILTERS)[number]>('all')
const rooms = ref<RoomSummary[]>([])
const error = ref<ApiError | null>(null)
const loaded = ref(false)
const codeInput = ref('')

const ENDED = ['finished', 'aborted', 'expired']

const shown = computed(() => {
  const list = [...rooms.value].sort((a, b) => b.created_at.localeCompare(a.created_at))
  if (filter.value === 'all') return list
  if (filter.value === 'finished') return list.filter((r) => ENDED.includes(r.status))
  return list.filter((r) => r.status === filter.value)
})

async function refresh() {
  try {
    rooms.value = await api.rooms()
    error.value = null
  } catch (e) {
    error.value = e as ApiError
  } finally {
    loaded.value = true
  }
}

function open(room: RoomSummary) {
  const ended = ENDED.includes(room.status) && room.status !== 'expired'
  router.push(ended ? `/rooms/${room.room_code}/replay` : `/rooms/${room.room_code}`)
}

function go() {
  const code = codeInput.value.trim().toUpperCase()
  if (code) router.push(`/rooms/${code}`)
}

let timer = 0
onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 3000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="page">
    <div class="top">
      <h1>{{ t('lobby.title') }}</h1>
      <form class="goto" @submit.prevent="go">
        <input v-model="codeInput" :placeholder="t('lobby.codePlaceholder')" maxlength="6" autocomplete="off" />
        <button type="submit">{{ t('lobby.go') }}</button>
      </form>
    </div>

    <nav class="filters">
      <button v-for="f in FILTERS" :key="f" :class="{ active: filter === f }" @click="filter = f">
        {{ t(`lobby.filter.${f}`) }}
      </button>
    </nav>

    <div v-if="error" class="notice error">{{ error.code === 'network_error' ? t('error.network') : error.message }}</div>

    <table v-if="shown.length" class="rooms">
      <thead>
        <tr>
          <th>{{ t('lobby.code') }}</th>
          <th>{{ t('lobby.status') }}</th>
          <th v-for="s in SEATS" :key="s" class="seat-col">{{ t(`seat.${s}`) }}</th>
          <th>{{ t('lobby.progress') }}</th>
          <th>{{ t('lobby.created') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in shown" :key="r.room_code" tabindex="0" @click="open(r)" @keydown.enter="open(r)">
          <td class="code">{{ r.room_code }}</td>
          <td><StatusBadge :status="r.status" /></td>
          <td v-for="s in SEATS" :key="s" class="seat-col" :class="{ empty: !r.seats[s] }">
            {{ r.seats[s] ?? t('room.empty') }}
          </td>
          <td>{{ r.board_index }} / {{ r.boards }}</td>
          <td class="muted">{{ formatTime(r.created_at, locale) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else-if="loaded && !error" class="muted empty-list">{{ t('lobby.empty') }}</p>
  </div>
</template>

<style scoped>
.top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
.goto {
  display: flex;
  gap: 6px;
}
.goto input {
  width: 9em;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.filters {
  display: flex;
  gap: 6px;
  margin: 16px 0 12px;
}
.filters button {
  background: transparent;
  color: var(--muted);
  border-color: var(--line);
}
.filters button.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.rooms {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--line);
}
th,
td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--line);
  font-size: 0.9rem;
}
th {
  font-size: 0.78rem;
  color: var(--muted);
}
tbody tr {
  cursor: pointer;
}
tbody tr:hover td,
tbody tr:focus-visible td {
  background: var(--row-alt);
  outline: none;
}
.code {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.seat-col {
  max-width: 10em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
td.empty {
  color: var(--muted);
}
.empty-list {
  padding: 40px 0;
  text-align: center;
}
@media (max-width: 760px) {
  .seat-col {
    display: none;
  }
}
</style>

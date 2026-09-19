<script setup lang="ts">
// 回放:房間結束後,一步一步重播每一副牌,四家全開。
// 每一步的畫面都由平台用 bridge-core 重播算好,前端只負責切換。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import BridgeTable from '../components/BridgeTable.vue'
import AuctionTable from '../components/AuctionTable.vue'
import ResultsTable from '../components/ResultsTable.vue'
import StatusBadge from '../components/StatusBadge.vue'
import CallText from '../components/CallText.vue'
import PlayingCard from '../components/PlayingCard.vue'
import { ApiError, api } from '../api/client'
import { useI18n } from '../i18n'
import { useDescribe } from '../describe'
import { SEATS, type Replay, type RoomRecord, type Seat } from '../api/types'

const props = defineProps<{ code: string }>()
const { t } = useI18n()
const describe = useDescribe()
const route = useRoute()
const router = useRouter()

const record = ref<RoomRecord | null>(null)
const replay = ref<Replay | null>(null)
const error = ref<ApiError | null>(null)
const index = ref(Number(route.query.board) || 1) // 第幾副(1 開始),不是牌號
const step = ref(0)
const playing = ref(false)
const speed = ref(1000)

const names = computed(() => {
  const out: Partial<Record<Seat, string | null>> = {}
  for (const s of SEATS) out[s] = record.value?.players[s]?.name ?? null
  return out
})

// 分頁上顯示牌號。board_id 是「房號-牌號」
const tabs = computed(() =>
  (record.value?.deals ?? []).map((d, i) => ({
    index: i + 1,
    board: Number(String(d.board_id ?? '').split('-').pop()) || i + 1,
    incomplete: !!d.incomplete,
  })),
)

const frames = computed(() => replay.value?.frames ?? [])
const last = computed(() => Math.max(0, frames.value.length - 1))
const frame = computed(() => frames.value[Math.min(step.value, last.value)] ?? null)

// 叫牌結束、開始出牌的那一步,方便直接跳過去
const firstPlay = computed(() => frames.value.findIndex((f) => f.action?.phase === 'play'))

async function loadRecord() {
  try {
    record.value = await api.record(props.code)
    error.value = null
  } catch (e) {
    error.value = e as ApiError
  }
}

async function loadBoard() {
  if (!record.value) return
  stopPlay()
  replay.value = null
  try {
    replay.value = await api.replay(props.code, index.value)
    step.value = 0
  } catch (e) {
    error.value = e as ApiError
  }
}

function selectBoard(i: number) {
  if (i === index.value) return
  index.value = i
  router.replace({ query: { ...route.query, board: String(i) } })
}

function selectByBoardNumber(board: number) {
  const tab = tabs.value.find((x) => x.board === board)
  if (tab) selectBoard(tab.index)
}

function go(to: number) {
  step.value = Math.min(Math.max(0, to), last.value)
}

let timer = 0
function stopPlay() {
  playing.value = false
  window.clearInterval(timer)
}
function togglePlay() {
  if (playing.value) return stopPlay()
  if (step.value >= last.value) step.value = 0
  playing.value = true
  const tick = () => {
    if (step.value >= last.value) stopPlay()
    else step.value++
  }
  timer = window.setInterval(tick, speed.value)
}
watch(speed, () => {
  if (playing.value) {
    stopPlay()
    togglePlay()
  }
})

function onKey(e: KeyboardEvent) {
  if ((e.target as HTMLElement)?.closest('input, select, textarea')) return
  if (e.key === 'ArrowRight') go(step.value + 1)
  else if (e.key === 'ArrowLeft') go(step.value - 1)
  else if (e.key === 'Home') go(0)
  else if (e.key === 'End') go(last.value)
  else if (e.key === ' ') {
    e.preventDefault()
    togglePlay()
  } else return
  e.preventDefault()
  if (e.key !== ' ') stopPlay()
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  await loadRecord()
  if (record.value && (index.value < 1 || index.value > record.value.deals.length)) index.value = 1
  await loadBoard()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  stopPlay()
})
watch(index, loadBoard)
</script>

<template>
  <div class="page">
    <div v-if="error" class="notice error">
      <template v-if="error.code === 'room_not_ended'">
        {{ t('replay.notEnded') }} <RouterLink :to="`/rooms/${code}`">{{ t('replay.toLive') }}</RouterLink>
      </template>
      <template v-else-if="error.code === 'room_not_found'">{{ t('room.notFound', { code }) }}</template>
      <template v-else-if="error.code === 'network_error'">{{ t('error.network') }}</template>
      <template v-else>{{ error.message || error.code }}</template>
    </div>

    <div v-else-if="!record" class="notice">{{ t('common.loading') }}</div>

    <template v-else>
      <header class="bar">
        <h1>
          {{ t('replay.title', { code: record.room_code }) }}
          <StatusBadge :status="record.status" />
        </h1>
        <span class="muted">{{ describe.endReason(record) }}</span>
      </header>

      <div v-if="!tabs.length" class="notice">{{ t('replay.noBoards') }}</div>

      <template v-else>
        <nav class="tabs">
          <button
            v-for="tab in tabs"
            :key="tab.index"
            :class="{ active: tab.index === index }"
            :title="tab.incomplete ? t('replay.incomplete') : ''"
            @click="selectBoard(tab.index)"
          >
            {{ t('replay.boardTab', { n: tab.board }) }}<span v-if="tab.incomplete">*</span>
          </button>
        </nav>

        <div class="layout">
          <div class="main">
            <BridgeTable v-if="frame" :view="frame.view" :names="names" />
            <div v-else class="notice">{{ t('common.loading') }}</div>

            <div v-if="frame" class="controls">
              <div class="buttons">
                <button :title="t('replay.first')" @click="stopPlay(), go(0)">⏮</button>
                <button :title="t('replay.prev')" @click="stopPlay(), go(step - 1)">◀</button>
                <button class="play" :title="t(playing ? 'replay.pause' : 'replay.play')" @click="togglePlay">
                  {{ playing ? '⏸' : '▶' }}
                </button>
                <button :title="t('replay.next')" @click="stopPlay(), go(step + 1)">▶|</button>
                <button :title="t('replay.last')" @click="stopPlay(), go(last)">⏭</button>
                <button v-if="firstPlay > 0" class="text" @click="stopPlay(), go(firstPlay)">
                  {{ t('replay.toPlay') }}
                </button>
                <select v-model.number="speed" :aria-label="t('replay.speed')">
                  <option :value="2000">0.5×</option>
                  <option :value="1000">1×</option>
                  <option :value="400">2.5×</option>
                  <option :value="150">6×</option>
                </select>
              </div>
              <input
                v-model.number="step"
                class="slider"
                type="range"
                min="0"
                :max="last"
                :aria-label="t('replay.step')"
                @input="stopPlay"
              />
              <div class="step-info">
                <span class="muted">{{ step }} / {{ last }}</span>
                <span v-if="!frame.action">{{ t('replay.dealt') }}</span>
                <span v-else-if="frame.action.phase === 'bid'">
                  {{ t('replay.bidBy', { seat: t(`seat.${frame.action.seat}`) }) }}
                  <CallText :call="frame.action.action" />
                </span>
                <span v-else class="played">
                  {{ t('replay.playBy', { seat: t(`seat.${frame.action.seat}`) }) }}
                  <span v-if="frame.action.actor !== frame.action.seat" class="muted">
                    ({{ t('room.byDeclarer', { seat: t(`seat.${frame.action.actor}`) }) }})
                  </span>
                  <PlayingCard :card="frame.action.action" class="mini" />
                </span>
              </div>
              <p class="muted keys">{{ t('replay.keys') }}</p>
            </div>
          </div>

          <aside class="side">
            <section v-if="frame" class="panel">
              <h2>{{ t('table.auction') }}</h2>
              <AuctionTable
                :auction="frame.view.auction"
                :dealer="frame.view.dealer"
                :vulnerability="frame.view.vulnerability"
              />
            </section>
            <section class="panel">
              <h2>{{ t('result.title') }}</h2>
              <ResultsTable :results="record.results" :current="replay?.board" @select="selectByBoardNumber" />
            </section>
          </aside>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
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
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}
.tabs button {
  background: transparent;
  color: var(--muted);
  border-color: var(--line);
}
.tabs button.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
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
.controls {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.buttons button {
  min-width: 2.6em;
}
.buttons .play {
  min-width: 3.4em;
}
.buttons select {
  margin-left: auto;
}
.slider {
  width: 100%;
  margin: 10px 0 6px;
  accent-color: var(--accent);
}
.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 34px;
}
.played {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.mini {
  --card-w: 24px;
  --card-h: 34px;
}
.mini :deep(.pip) {
  display: none;
}
.keys {
  margin: 4px 0 0;
  font-size: 0.78rem;
}
@media (max-width: 1100px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>

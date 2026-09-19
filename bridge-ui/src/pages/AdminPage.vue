<script setup lang="ts">
// 主辦方頁面:輸入金鑰、開房(隨機或指定牌)、終止房間、四家全開觀看。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, api } from '../api/client'
import { useAdminKey } from '../composables/useAdminKey'
import { useI18n } from '../i18n'
import { formatTime } from '../format'
import { SEATS, type RoomSummary } from '../api/types'

const { t, locale } = useI18n()
const key = useAdminKey()

// -- 金鑰 -------------------------------------------------------------------

const keyInput = ref('')
const keyState = ref<'idle' | 'checking' | 'bad' | 'disabled' | 'error'>('idle')

// 平台沒有專門驗證金鑰的端點,查一個不存在的房間:404 代表金鑰對
async function checkKey(candidate: string): Promise<boolean> {
  try {
    await api.admin.room(candidate, 'ZZZZZZ')
    return true
  } catch (e) {
    const err = e as ApiError
    if (err.code === 'room_not_found') return true
    keyState.value = err.code === 'admin_disabled' ? 'disabled' : err.status === 401 ? 'bad' : 'error'
    return false
  }
}

async function login() {
  const candidate = keyInput.value.trim()
  if (!candidate) return
  keyState.value = 'checking'
  if (await checkKey(candidate)) {
    key.value = candidate
    keyInput.value = ''
    keyState.value = 'idle'
    refresh()
  }
}

function logout() {
  key.value = ''
}

// -- 開房 -------------------------------------------------------------------

const mode = ref<'random' | 'pbn'>('random')
const boards = ref(4)
const seed = ref<string>('')
const firstBoard = ref(1)
const pbnText = ref('')
const creating = ref(false)
const createError = ref('')
const created = ref<RoomSummary | null>(null)

// 每行一副:「牌號 PBN」,例如 7 N:862.62.AQT52.A96 AQJT9.Q875.97.K7 ...
function parsePbn(text: string) {
  const out: { number: number; deal: string }[] = []
  for (const [i, raw] of text.split('\n').entries()) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const m = line.match(/^(\d+)\s+(.+)$/)
    if (!m) throw new Error(t('admin.pbnLineError', { n: i + 1 }))
    out.push({ number: Number(m[1]), deal: m[2].trim() })
  }
  if (!out.length) throw new Error(t('admin.pbnEmpty'))
  return out
}

async function create() {
  createError.value = ''
  created.value = null
  let body: unknown
  try {
    if (mode.value === 'pbn') {
      body = { boards: parsePbn(pbnText.value) }
    } else {
      const options: Record<string, number> = { boards: boards.value, first_board: firstBoard.value }
      if (seed.value.trim() !== '') {
        const n = Number(seed.value)
        if (!Number.isInteger(n)) throw new Error(t('admin.seedError'))
        options.seed = n
      }
      body = { options }
    }
  } catch (e) {
    createError.value = (e as Error).message
    return
  }
  creating.value = true
  try {
    created.value = await api.admin.create(key.value, body)
    refresh()
  } catch (e) {
    const err = e as ApiError
    createError.value = err.message || err.code
    if (err.code === 'invalid_admin_key') logout()
  } finally {
    creating.value = false
  }
}

// -- 房間列表 ---------------------------------------------------------------

const rooms = ref<RoomSummary[]>([])
const active = computed(() =>
  [...rooms.value]
    .filter((r) => r.status === 'waiting' || r.status === 'playing')
    .sort((a, b) => b.created_at.localeCompare(a.created_at)),
)

async function refresh() {
  try {
    rooms.value = await api.rooms()
  } catch {
    /* 列表抓不到不影響其他功能,下次再試 */
  }
}

async function abort(room: RoomSummary) {
  if (!window.confirm(t('admin.confirmAbort', { code: room.room_code }))) return
  try {
    await api.admin.abort(key.value, room.room_code)
  } catch (e) {
    window.alert((e as ApiError).message)
  }
  refresh()
}

let timer = 0
onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 3000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="page narrow">
    <h1>{{ t('admin.title') }}</h1>

    <section v-if="!key" class="panel">
      <h2>{{ t('admin.keyTitle') }}</h2>
      <p class="muted">{{ t('admin.keyHelp') }}</p>
      <form class="row" @submit.prevent="login">
        <input v-model="keyInput" type="password" autocomplete="off" :placeholder="t('admin.keyPlaceholder')" />
        <button type="submit" :disabled="keyState === 'checking'">{{ t('admin.login') }}</button>
      </form>
      <p v-if="keyState === 'bad'" class="err">{{ t('admin.badKey') }}</p>
      <p v-else-if="keyState === 'disabled'" class="err">{{ t('admin.disabled') }}</p>
      <p v-else-if="keyState === 'error'" class="err">{{ t('error.network') }}</p>
    </section>

    <template v-else>
      <div class="row end">
        <span class="muted">{{ t('admin.loggedIn') }}</span>
        <button class="text" @click="logout">{{ t('admin.logout') }}</button>
      </div>

      <section class="panel">
        <h2>{{ t('admin.createTitle') }}</h2>
        <div class="modes">
          <label><input v-model="mode" type="radio" value="random" /> {{ t('admin.modeRandom') }}</label>
          <label><input v-model="mode" type="radio" value="pbn" /> {{ t('admin.modePbn') }}</label>
        </div>

        <form @submit.prevent="create">
          <div v-if="mode === 'random'" class="fields">
            <label>
              {{ t('admin.boards') }}
              <input v-model.number="boards" type="number" min="1" max="32" required />
            </label>
            <label>
              {{ t('admin.firstBoard') }}
              <input v-model.number="firstBoard" type="number" min="1" max="10000" required />
            </label>
            <label>
              {{ t('admin.seed') }}
              <input v-model="seed" inputmode="numeric" :placeholder="t('admin.seedPlaceholder')" />
            </label>
          </div>
          <div v-else>
            <p class="muted small">{{ t('admin.pbnHelp') }}</p>
            <textarea
              v-model="pbnText"
              rows="6"
              spellcheck="false"
              placeholder="1 N:AK97543.K.T3.AK7 ..."
            />
          </div>
          <div class="row">
            <button type="submit" :disabled="creating">{{ t('admin.create') }}</button>
            <span v-if="createError" class="err">{{ createError }}</span>
          </div>
        </form>

        <div v-if="created" class="created">
          {{ t('admin.created') }}
          <strong class="code">{{ created.room_code }}</strong>
          <span class="muted">{{ t('admin.createdHint') }}</span>
          <RouterLink :to="`/admin/rooms/${created.room_code}`">{{ t('admin.watchAll') }}</RouterLink>
        </div>
      </section>

      <section class="panel">
        <h2>{{ t('admin.activeTitle') }}</h2>
        <table v-if="active.length" class="rooms">
          <tbody>
            <tr v-for="r in active" :key="r.room_code">
              <td class="code">{{ r.room_code }}</td>
              <td><StatusBadge :status="r.status" /></td>
              <td class="muted">
                {{ SEATS.filter((s) => r.seats[s]).length }}/4 · {{ r.board_index }}/{{ r.boards }} ·
                {{ formatTime(r.created_at, locale) }}
              </td>
              <td class="actions">
                <RouterLink :to="`/admin/rooms/${r.room_code}`">{{ t('admin.watchAll') }}</RouterLink>
                <button class="danger" @click="abort(r)">{{ t('admin.abort') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">{{ t('admin.noActive') }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
h1 {
  font-size: 1.4rem;
  margin: 0 0 16px;
}
.panel {
  padding: 14px 16px;
  margin-bottom: 16px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.panel h2 {
  margin: 0 0 10px;
  font-size: 1rem;
}
.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.row.end {
  justify-content: flex-end;
  margin: 0 0 8px;
}
.row input {
  flex: 1;
  min-width: 200px;
}
.modes {
  display: flex;
  gap: 16px;
  margin-bottom: 10px;
}
.fields {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.fields label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
  color: var(--muted);
}
.fields input {
  width: 10em;
}
textarea {
  width: 100%;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.85rem;
}
.small {
  font-size: 0.82rem;
}
.err {
  color: var(--danger);
  font-size: 0.88rem;
}
.created {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--accent-soft);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
}
.code {
  font-family: ui-monospace, Consolas, monospace;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.rooms {
  width: 100%;
  border-collapse: collapse;
}
.rooms td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--line);
  font-size: 0.9rem;
}
.actions {
  text-align: right;
  white-space: nowrap;
}
.actions a {
  margin-right: 10px;
}
</style>

<script setup lang="ts">
// 叫牌表。照慣例西北東南四欄,從發牌者那一欄開始填。
import { computed } from 'vue'
import CallText from './CallText.vue'
import { useI18n } from '../i18n'
import { isVulnerable } from '../format'
import type { Call, Seat, Vulnerability } from '../api/types'

const props = defineProps<{
  auction: Call[]
  dealer: Seat
  vulnerability: Vulnerability
  waiting?: boolean // 叫牌還在進行,最後放一個問號
}>()
const { t } = useI18n()

const COLUMNS: Seat[] = ['W', 'N', 'E', 'S']

const rows = computed(() => {
  const cells: (string | null)[] = Array(COLUMNS.indexOf(props.dealer)).fill(null)
  for (const c of props.auction) cells.push(c.bid)
  if (props.waiting) cells.push('?')
  const out: (string | null)[][] = []
  for (let i = 0; i < cells.length; i += 4) out.push(cells.slice(i, i + 4))
  return out
})
</script>

<template>
  <table class="auction">
    <thead>
      <tr>
        <th v-for="s in COLUMNS" :key="s" :class="{ vul: isVulnerable(s, vulnerability) }">
          {{ t(`seat.${s}`) }}<span v-if="s === dealer" class="dealer" :title="t('table.dealer')">D</span>
        </th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(row, i) in rows" :key="i">
        <td v-for="col in 4" :key="col">
          <template v-if="row[col - 1] === '?'"><span class="waiting">?</span></template>
          <CallText v-else-if="row[col - 1]" :call="row[col - 1]!" />
        </td>
      </tr>
      <tr v-if="!rows.length">
        <td colspan="4" class="empty">{{ t('table.noBids') }}</td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.auction {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 0.95rem;
}
th {
  font-size: 0.8rem;
  font-weight: 600;
  padding: 4px 2px;
  border-radius: 4px 4px 0 0;
  background: var(--nonvul-bg);
  color: var(--text);
}
th.vul {
  background: var(--vul-bg);
  color: #fff;
}
.dealer {
  display: inline-block;
  margin-left: 4px;
  padding: 0 4px;
  font-size: 0.7rem;
  border-radius: 3px;
  background: var(--surface);
  color: var(--text);
}
td {
  text-align: center;
  padding: 3px 2px;
  height: 1.7em;
}
tbody tr:nth-child(even) td {
  background: var(--row-alt);
}
.waiting {
  color: var(--accent);
  font-weight: 700;
  animation: blink 1.2s infinite;
}
.empty {
  color: var(--muted);
  font-size: 0.85rem;
}
@keyframes blink {
  50% {
    opacity: 0.3;
  }
}
</style>

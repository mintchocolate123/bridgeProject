<script setup lang="ts">
// 各副牌的結果與南北累計分數
import { computed } from 'vue'
import ContractText from './ContractText.vue'
import { useI18n } from '../i18n'
import { overUnder, signed } from '../format'
import type { BoardResult } from '../api/types'

const props = defineProps<{ results: BoardResult[]; current?: number | null }>()
const emit = defineEmits<{ (e: 'select', board: number): void }>()
const { t } = useI18n()

const total = computed(() => props.results.reduce((sum, r) => sum + r.ns_score, 0))
</script>

<template>
  <table class="results">
    <thead>
      <tr>
        <th>{{ t('result.board') }}</th>
        <th>{{ t('result.contract') }}</th>
        <th>{{ t('result.declarer') }}</th>
        <th>{{ t('result.made') }}</th>
        <th class="num">{{ t('side.NS') }}</th>
        <th class="num">{{ t('side.EW') }}</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="r in results"
        :key="r.board"
        :class="{ current: r.board === current }"
        @click="emit('select', r.board)"
      >
        <td>{{ r.board }}</td>
        <td><ContractText :contract="r.contract" :passed-out="r.passed_out" /></td>
        <td>{{ r.declarer ? t(`seatShort.${r.declarer}`) : '' }}</td>
        <td :title="r.tricks !== null ? t('result.tricksTitle', { n: r.tricks }) : ''">
          {{ r.contract && r.tricks !== null ? overUnder(r.contract.level, r.tricks) : '' }}
        </td>
        <td class="num">{{ r.ns_score > 0 ? r.ns_score : '' }}</td>
        <td class="num">{{ r.ns_score < 0 ? -r.ns_score : '' }}</td>
      </tr>
      <tr v-if="!results.length">
        <td colspan="6" class="empty">{{ t('result.none') }}</td>
      </tr>
    </tbody>
    <tfoot v-if="results.length">
      <tr>
        <td colspan="4">{{ t('result.totalNS') }}</td>
        <td colspan="2" class="num total">{{ signed(total) }}</td>
      </tr>
    </tfoot>
  </table>
</template>

<style scoped>
.results {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
th,
td {
  padding: 4px 5px;
  text-align: left;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
th {
  font-size: 0.78rem;
  color: var(--muted);
  font-weight: 600;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
tbody tr {
  cursor: pointer;
}
tbody tr:hover td {
  background: var(--row-alt);
}
tr.current td {
  background: var(--accent-soft);
}
.empty {
  color: var(--muted);
  cursor: default;
}
tfoot td {
  font-weight: 700;
  border-bottom: none;
}
</style>

<script setup lang="ts">
// 合約,例如 4♠X by S
import { useI18n } from '../i18n'
import { isRed, strainText } from '../format'
import type { Contract } from '../api/types'

defineProps<{ contract: Contract | null; passedOut?: boolean; withDeclarer?: boolean }>()
const { t } = useI18n()
</script>

<template>
  <span v-if="passedOut" class="contract passed">{{ t('result.passedOut') }}</span>
  <span v-else-if="contract" class="contract">
    {{ contract.level }}<span :class="{ red: isRed(contract.strain) }">{{ strainText(contract.strain) }}</span
    ><span v-if="contract.doubled === 'doubled'" class="dbl">X</span
    ><span v-else-if="contract.doubled === 'redoubled'" class="dbl">XX</span>
    <span v-if="withDeclarer" class="by">{{ t('result.by', { seat: t(`seat.${contract.declarer}`) }) }}</span>
  </span>
  <span v-else class="contract none">—</span>
</template>

<style scoped>
.contract {
  font-weight: 700;
  white-space: nowrap;
}
.red {
  color: var(--card-red);
}
.dbl {
  color: var(--danger);
  margin-left: 1px;
}
.by {
  font-weight: 400;
  color: var(--muted);
  margin-left: 0.3em;
}
.passed,
.none {
  color: var(--muted);
  font-weight: 500;
}
</style>

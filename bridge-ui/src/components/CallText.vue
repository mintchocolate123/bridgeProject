<script setup lang="ts">
// 一個叫品:1♥ 的花色上色,P / X / XX 依語言顯示
import { computed } from 'vue'
import { useI18n } from '../i18n'
import { isRed, parseCall, strainText } from '../format'

const props = defineProps<{ call: string }>()
const { t } = useI18n()
const parsed = computed(() => parseCall(props.call))
</script>

<template>
  <span v-if="parsed.kind === 'bid'" class="call">
    {{ parsed.level }}<span :class="{ red: isRed(parsed.strain!) }">{{ strainText(parsed.strain!) }}</span>
  </span>
  <span v-else class="call" :class="parsed.kind">{{ t(`call.${parsed.kind}`) }}</span>
</template>

<style scoped>
.call {
  font-weight: 600;
  white-space: nowrap;
}
.red {
  color: var(--card-red);
}
.pass {
  color: var(--muted);
  font-weight: 500;
}
.double {
  color: var(--danger);
}
.redouble {
  color: var(--info);
}
</style>

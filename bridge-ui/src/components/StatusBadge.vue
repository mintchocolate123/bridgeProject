<script setup lang="ts">
import { useI18n } from '../i18n'
import type { RoomStatus } from '../api/types'

defineProps<{ status: RoomStatus }>()
const { t } = useI18n()
</script>

<template>
  <span class="badge" :class="status">{{ t(`status.${status}`) }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
  background: var(--row-alt);
  color: var(--muted);
}
.playing {
  background: var(--accent-soft);
  color: var(--accent-strong);
}
.waiting {
  background: var(--info-soft);
  color: var(--info);
}
.aborted {
  background: var(--danger-soft);
  color: var(--danger);
}
</style>

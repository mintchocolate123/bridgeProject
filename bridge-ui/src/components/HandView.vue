<script setup lang="ts">
// 一家的手牌,疊成一排。看不到的牌(cards 為 null)依張數畫牌背。
import { computed } from 'vue'
import PlayingCard from './PlayingCard.vue'
import { sortCards } from '../format'

const props = defineProps<{
  cards: string[] | null
  count: number
  legal?: string[] // 有給就代表這手牌可以點(之後真人對局用)
}>()
const emit = defineEmits<{ (e: 'pick', card: string): void }>()

// 換花色時多留一點空隙,比較好讀
const items = computed(() => {
  if (!props.cards) return Array.from({ length: props.count }, (_, i) => ({ key: `b${i}`, card: null, gap: false }))
  const sorted = sortCards(props.cards)
  return sorted.map((card, i) => ({ key: card, card, gap: i > 0 && sorted[i - 1][0] !== card[0] }))
})
</script>

<template>
  <div class="hand" :class="{ hidden: !cards }">
    <div v-for="item in items" :key="item.key" class="slot" :class="{ gap: item.gap }">
      <PlayingCard
        :card="item.card"
        :playable="!!legal && !!item.card && legal.includes(item.card)"
        :dim="!!legal && !!item.card && !legal.includes(item.card)"
        @pick="emit('pick', $event)"
      />
    </div>
    <div v-if="count === 0" class="empty" />
  </div>
</template>

<style scoped>
.hand {
  display: flex;
  justify-content: center;
  min-height: var(--card-h);
  padding-top: 10px; /* 可點的牌會往上浮 */
}
.slot + .slot {
  margin-left: calc(var(--card-w) * -0.56);
}
.slot.gap {
  margin-left: calc(var(--card-w) * -0.4);
}
.hidden .slot + .slot {
  margin-left: calc(var(--card-w) * -0.8);
}
.empty {
  height: var(--card-h);
}
</style>

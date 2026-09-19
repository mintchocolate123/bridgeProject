<script setup lang="ts">
// 一張牌。card 為 null 時畫牌背。全部用 CSS 畫,不需要圖檔。
import { computed } from 'vue'
import { SUIT_SYMBOL, isRed, parseCard } from '../format'

const props = defineProps<{
  card: string | null
  playable?: boolean
  dim?: boolean
  highlight?: boolean
}>()
const emit = defineEmits<{ (e: 'pick', card: string): void }>()

const parts = computed(() => (props.card ? parseCard(props.card) : null))
const label = computed(() => (parts.value ? `${SUIT_SYMBOL[parts.value.suit]}${parts.value.rank}` : 'card back'))

function pick() {
  if (props.playable && props.card) emit('pick', props.card)
}
</script>

<template>
  <div
    class="card"
    :class="{
      back: !card,
      red: parts && isRed(parts.suit),
      playable,
      dim,
      highlight,
    }"
    :role="playable ? 'button' : undefined"
    :tabindex="playable ? 0 : undefined"
    :aria-label="label"
    @click="pick"
    @keydown.enter="pick"
  >
    <template v-if="parts">
      <span class="corner">
        <span class="rank">{{ parts.rank }}</span>
        <span class="suit">{{ SUIT_SYMBOL[parts.suit] }}</span>
      </span>
      <span class="pip">{{ SUIT_SYMBOL[parts.suit] }}</span>
    </template>
  </div>
</template>

<style scoped>
.card {
  position: relative;
  flex: none;
  width: var(--card-w);
  height: var(--card-h);
  border-radius: calc(var(--card-w) * 0.1);
  background: var(--card-face);
  border: 1px solid var(--card-edge);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.25);
  color: var(--card-black);
  user-select: none;
  transition: transform 0.12s ease, opacity 0.2s ease;
}
.card.red {
  color: var(--card-red);
}
.corner {
  position: absolute;
  top: 3px;
  left: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1;
  font-weight: 700;
  font-size: calc(var(--card-w) * 0.28);
}
.corner .rank {
  letter-spacing: -0.08em;
}
.corner .suit {
  font-size: 0.85em;
}
.pip {
  position: absolute;
  right: 6%;
  bottom: 4%;
  font-size: calc(var(--card-w) * 0.55);
  line-height: 1;
  opacity: 0.9;
}
.card.back {
  background:
    repeating-linear-gradient(45deg, var(--back-a) 0 4px, var(--back-b) 4px 8px);
  border: 3px solid var(--card-face);
  outline: 1px solid var(--card-edge);
}
.card.dim {
  opacity: 0.45;
}
.card.highlight {
  box-shadow: 0 0 0 3px var(--accent);
}
.card.playable {
  cursor: pointer;
}
.card.playable:hover,
.card.playable:focus-visible {
  transform: translateY(-10px);
  outline: none;
}
</style>

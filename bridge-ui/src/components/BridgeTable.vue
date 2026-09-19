<script setup lang="ts">
// 牌桌。只負責把「某個視角看到的狀態」畫出來,不管資料從哪裡來:
// 觀戰、主辦方、回放都用它。之後做真人對局時,傳入 playable 就能點牌出牌。
import { computed } from 'vue'
import HandView from './HandView.vue'
import PlayingCard from './PlayingCard.vue'
import ContractText from './ContractText.vue'
import { useI18n } from '../i18n'
import { isVulnerable, overUnder, signed } from '../format'
import type { DealView, PlayedCard, Seat } from '../api/types'

const props = defineProps<{
  view: DealView
  names?: Partial<Record<Seat, string | null>>
  playable?: { seat: Seat; legal: string[] } // 預留給真人對局
}>()
const emit = defineEmits<{ (e: 'play', card: string): void }>()
const { t } = useI18n()

const SEAT_AREAS: Seat[] = ['N', 'W', 'E', 'S']

// 本墩還沒開始出牌時,把上一墩淡淡地留在桌上,不然四張牌一湊齊就消失,看不到誰贏
const trick = computed<{ cards: PlayedCard[]; last: boolean; winner: Seat | null }>(() => {
  const v = props.view
  if (v.current_trick.length) return { cards: v.current_trick, last: false, winner: null }
  const prev = v.tricks[v.tricks.length - 1]
  if (prev) return { cards: prev.cards, last: true, winner: prev.winner }
  return { cards: [], last: false, winner: null }
})

function trickCard(seat: Seat): string | null {
  return trick.value.cards.find((c) => c.seat === seat)?.card ?? null
}

function role(seat: Seat): string | null {
  if (!props.view.contract) return null
  if (seat === props.view.declarer) return t('table.declarer')
  if (seat === props.view.dummy) return t('table.dummy')
  return null
}

const turnSeat = computed(() => props.view.turn?.seat ?? null)
const result = computed(() => props.view.result)
</script>

<template>
  <div class="table">
    <section v-for="seat in SEAT_AREAS" :key="seat" class="seat" :class="[`seat-${seat}`, { turn: turnSeat === seat }]">
      <header class="plate" :class="{ vul: isVulnerable(seat, view.vulnerability) }">
        <span class="dir">{{ t(`seat.${seat}`) }}</span>
        <span class="name" :title="names?.[seat] ?? ''">{{ names?.[seat] ?? '—' }}</span>
        <span v-if="view.dealer === seat" class="tag dealer" :title="t('table.dealer')">D</span>
        <span v-if="role(seat)" class="tag role">{{ role(seat) }}</span>
      </header>
      <HandView
        :cards="view.hands[seat]"
        :count="view.hand_counts[seat]"
        :legal="playable && view.turn?.seat === seat ? playable.legal : undefined"
        @pick="emit('play', $event)"
      />
    </section>

    <div class="center">
      <div class="felt">
        <div v-for="seat in ['N', 'E', 'S', 'W'] as Seat[]" :key="seat" class="played" :class="`at-${seat}`">
          <PlayingCard
            v-if="trickCard(seat)"
            :card="trickCard(seat)"
            :dim="trick.last && trick.winner !== seat"
            :highlight="trick.last && trick.winner === seat"
          />
        </div>

        <div v-if="!result || result.passed_out" class="middle">
          <template v-if="view.phase === 'bidding'">
            <span class="phase">{{ t('table.bidding') }}</span>
          </template>
          <template v-else-if="view.passed_out">
            <span class="phase">{{ t('result.passedOut') }}</span>
          </template>
          <template v-else-if="view.contract">
            <ContractText :contract="view.contract" with-declarer />
            <span class="counts">
              <span>{{ t('side.NS') }} {{ view.counts.NS }}</span>
              <span>{{ t('side.EW') }} {{ view.counts.EW }}</span>
            </span>
          </template>
        </div>

        <div v-if="result && !result.passed_out && result.contract" class="final">
          <div class="final-line">
            <ContractText :contract="result.contract" with-declarer />
            <span class="ou">{{ overUnder(result.contract.level, result.tricks!) }}</span>
          </div>
          <div class="final-score">{{ t('result.nsScore') }} {{ signed(result.ns_score) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.table {
  --card-w: 54px;
  --card-h: 76px;
  display: grid;
  grid-template-columns: 1fr minmax(220px, 260px) 1fr;
  grid-template-areas:
    '. n .'
    'w c e'
    '. s .';
  gap: 12px 16px;
  align-items: center;
  padding: 16px;
  border-radius: 16px;
  background: var(--table-bg);
}
.seat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.seat-N {
  grid-area: n;
}
.seat-S {
  grid-area: s;
}
.seat-W {
  grid-area: w;
}
.seat-E {
  grid-area: e;
}
.center {
  grid-area: c;
}
.plate {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--plate-bg);
  color: var(--plate-text);
  font-size: 0.85rem;
  border: 2px solid transparent;
}
.plate.vul .dir {
  background: var(--vul-bg);
}
.dir {
  padding: 0 6px;
  border-radius: 4px;
  background: var(--nonvul-plate);
  font-weight: 700;
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 14em;
}
.tag {
  font-size: 0.7rem;
  padding: 0 5px;
  border-radius: 3px;
  background: rgb(255 255 255 / 0.2);
}
.turn .plate {
  border-color: var(--accent);
  box-shadow: 0 0 10px var(--accent);
}
.felt {
  position: relative;
  aspect-ratio: 1;
  border-radius: 14px;
  background: var(--felt);
  box-shadow: inset 0 0 24px rgb(0 0 0 / 0.35);
}
.played {
  position: absolute;
}
.at-N {
  top: 8%;
  left: 50%;
  transform: translateX(-50%);
}
.at-S {
  bottom: 8%;
  left: 50%;
  transform: translateX(-50%);
}
.at-W {
  left: 7%;
  top: 50%;
  transform: translateY(-50%);
}
.at-E {
  right: 7%;
  top: 50%;
  transform: translateY(-50%);
}
.middle {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  pointer-events: none;
  color: var(--felt-text);
  font-size: 0.85rem;
}
.middle :deep(.contract) {
  font-size: 0.9rem;
}
.middle :deep(.red) {
  color: #ff9d9d;
}
.middle :deep(.by) {
  color: var(--felt-text);
}
.counts {
  display: flex;
  gap: 8px;
  font-variant-numeric: tabular-nums;
}
.phase {
  opacity: 0.85;
}
.final {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  padding: 10px 16px;
  border-radius: 10px;
  background: var(--surface);
  color: var(--text);
  box-shadow: 0 4px 16px rgb(0 0 0 / 0.35);
  text-align: center;
  white-space: nowrap;
}
.final-line {
  font-size: 1.1rem;
}
.ou {
  margin-left: 6px;
  font-weight: 700;
}
.final-score {
  font-size: 0.85rem;
  color: var(--muted);
}

@media (max-width: 900px) {
  .table {
    --card-w: 40px;
    --card-h: 58px;
    grid-template-columns: 1fr minmax(150px, 190px) 1fr;
    padding: 10px;
    gap: 8px;
  }
}
@media (max-width: 620px) {
  .table {
    --card-w: 30px;
    --card-h: 44px;
    grid-template-columns: 1fr;
    grid-template-areas: 'n' 'c' 'w' 'e' 's';
  }
  .center {
    width: min(220px, 70vw);
    justify-self: center;
  }
}
</style>

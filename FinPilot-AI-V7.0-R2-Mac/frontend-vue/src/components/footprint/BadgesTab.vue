<script setup>
import { computed, ref } from 'vue'
import BadgeMedal from './BadgeMedal.vue'
import BadgeSlot from './BadgeSlot.vue'
import BadgeDetail from './BadgeDetail.vue'
import InfoTip from '@/components/InfoTip.vue'
import { BADGES, DEMO_BADGES, TIERS, progressOf } from '@/data/badges.js'
import { BADGE_PER_DAY } from '@/stores/footprint.js'

const rows = computed(() => BADGES.map((badge) => {
  return { badge, ...progressOf(badge) }
}))
const hero = computed(() => (DEMO_BADGES ? rows.value[0] : [...rows.value].filter((row) => row.next != null && row.badge.group !== 'hidden').sort((a, b) => b.pct - a.pct)[0] || rows.value[0]))
const opened = ref(null)
const groups = computed(() => [
  ['累計成就', rows.value.filter((row) => row.badge.group === 'total')],
  ['連續與隱藏', rows.value.filter((row) => row.badge.group !== 'total')],
])
const tierOf = (row) => (row.badge.goals.length === 1 ? 'gold' : TIERS[Math.max(0, row.earned - 1)][0])
const hiddenLocked = (row) => row.badge.group === 'hidden' && !row.earned
const total = computed(() => rows.value.reduce((sum, row) => sum + row.earned, 0))
const possible = BADGES.reduce((sum, badge) => sum + badge.goals.length, 0)
const dailyNote = `這一區每枚徽章每天最多累計 ${BADGE_PER_DAY} 次，隔天可以繼續。徽章記的是長期習慣，不用一天做完，也不用為了它多問 AI。`
</script>

<template>
  <section class="card surface-solid fp-card bg-hero" data-tour="fp-badge-hero">
    <button class="bg-hero-art" type="button" :aria-label="`打開${hero.badge.name}徽章`" @click="opened = hero.badge"><BadgeMedal :badge="hero.badge.id" :shape="hero.badge.shape" auto-sheen /></button>
    <div class="bg-hero-copy">
      <span v-if="DEMO_BADGES" class="fp-tag">展示用示範進度</span>
      <h2>{{ hero.badge.name }}</h2>
      <p>{{ hero.badge.desc }}</p>
      <div class="bg-meter" aria-hidden="true"><u :style="{ width: `${hero.pct}%` }"></u></div>
      <small>{{ hero.value }} / {{ hero.next ?? hero.badge.goals.at(-1) }} {{ hero.badge.unit }} · 點徽章可以旋轉、翻面</small>
    </div>
    <div class="bg-hero-tiers">
      <div v-for="([key, label], i) in TIERS" :key="key"><BadgeMedal :badge="hero.badge.id" :shape="hero.badge.shape" :tier="key" :locked="hero.earned <= i" /><small>{{ label }} · {{ hero.badge.goals[i] }} {{ hero.badge.unit }}</small></div>
    </div>
    <div class="bg-hero-total"><strong>{{ total }}</strong><small>/ {{ possible }} 階已解鎖</small></div>
  </section>
  <section v-for="[title, list] in groups" :key="title" class="card surface-solid fp-card fp-grow bg-group">
    <header><h2>{{ title }}<InfoTip v-if="title === '累計成就'" :text="dailyNote" label="累計規則" /></h2></header>
    <div class="bg-wall">
      <button v-for="row in list" :key="row.badge.id" class="bg-item" type="button" :disabled="hiddenLocked(row)" :title="row.badge.hint || row.badge.desc" @click="opened = row.badge">
        <div class="bg-art"><BadgeSlot v-if="hiddenLocked(row)" shape="shield" /><BadgeMedal v-else :badge="row.badge.id" :shape="row.badge.shape" :tier="tierOf(row)" :locked="!row.earned" /></div>
        <strong>{{ hiddenLocked(row) ? '？？？' : row.badge.name }}</strong>
        <small v-if="hiddenLocked(row)">{{ row.badge.hint }}</small>
        <small v-else-if="row.badge.group === 'hidden'">{{ row.badge.hint }}</small>
        <template v-else>
          <div class="bg-meter" aria-hidden="true"><u :style="{ width: `${row.pct}%` }"></u></div>
          <small>{{ row.value }} / {{ row.next ?? row.badge.goals.at(-1) }} {{ row.badge.unit }}</small>
        </template>
      </button>
    </div>
  </section>
  <BadgeDetail :badge="opened" @close="opened = null" />
</template>

<style scoped>
.bg-hero{flex:none;display:grid!important;grid-template-columns:128px minmax(0,1fr) auto auto;align-items:center;gap:18px;height:152px}
.bg-hero-art{width:128px;padding:0;border:0;background:transparent;cursor:pointer}
.bg-hero-copy{display:grid;justify-items:start;gap:3px;min-width:0}
.bg-hero-copy p{margin:0;color:var(--text);font-size:14px}
.bg-hero-copy small{color:var(--muted);font-size:12px}
.bg-hero-tiers{display:flex;gap:14px}
.bg-hero-tiers div{display:grid;justify-items:center;gap:4px;width:84px}
.bg-hero-tiers small{color:var(--muted);font-size:12px;white-space:nowrap}
.bg-hero-total{display:grid;justify-items:center;padding-left:18px;border-left:1px solid var(--line)}
.bg-hero-total strong{color:var(--text-strong);font-size:30px;line-height:1.1}
.bg-hero-total small{color:var(--muted);font-size:12px;white-space:nowrap}
.bg-meter{width:100%;max-width:280px;height:6px;border-radius:3px;background:var(--sc-track);overflow:hidden}
.bg-meter u{display:block;height:100%;border-radius:3px;background:var(--sc-a)}
.bg-group{gap:2px!important;padding-top:8px!important;padding-bottom:6px!important}
.bg-wall{flex:1;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;min-height:0}
.bg-item{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;min-width:0;min-height:0;padding:0;border:0;border-radius:12px;background:transparent;text-align:center;cursor:pointer}
.bg-item:disabled{cursor:default}
.bg-item:not(:disabled):hover{background:var(--sc-track)}
.bg-art{flex:0 1 74px;width:74px;min-height:0;aspect-ratio:1}
.bg-item strong{color:var(--text-strong);font-size:13px;white-space:nowrap}
.bg-item small{color:var(--muted);font-size:11px;line-height:1.25}
.bg-item .bg-meter{max-width:92px;height:5px}
@media (max-width:900px){.bg-hero{grid-template-columns:96px minmax(0,1fr);height:auto}.bg-hero-art{width:96px}.bg-hero-tiers,.bg-hero-total{display:none}.bg-wall{grid-template-columns:repeat(3,minmax(0,1fr))}}
</style>

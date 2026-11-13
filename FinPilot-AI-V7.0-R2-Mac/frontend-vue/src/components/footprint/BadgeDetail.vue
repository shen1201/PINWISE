<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppModal from '@/components/AppModal.vue'
import BadgeMedal from './BadgeMedal.vue'
import { METAL, ENAMEL, LOWER, SHAPE_PATHS, scalePath } from './medalShapes.js'
import { TIERS, progressOf } from '@/data/badges.js'

// 徽章大圖：可拖曳旋轉，放開後停在正面或背面；背面刻贏得日期。
const props = defineProps({ badge: { type: Object, default: null } })
const emit = defineEmits(['close'])
const tier = ref('gold')
const angle = ref(0)
const dragging = ref(false)
// 側邊由一層層薄片疊成：外緣倒角、溝線、中間一圈琺瑯色；靠正面的薄片挖空，看得到內壁。
const FRONT_Z = 11, ENAMEL_Z = 3, ART_Z = 7, BACK_Z = -11
const edges = computed(() => {
  const base = SHAPE_PATHS[props.badge?.shape] || SHAPE_PATHS.circle
  const [hi, mid, dark] = (METAL[tier.value] || METAL.gold).rim
  const enamel = (tier.value === 'gold' ? ENAMEL[props.badge?.id] || ENAMEL.verifier : LOWER[tier.value])[1]
  return Array.from({ length: 21 }, (_, i) => i - 10).map((z) => {
    const depth = Math.abs(z)
    const scale = depth === 10 ? 0.968 : depth === 9 ? 0.986 : 1
    const outer = scalePath(base, scale)
    const clip = z > ENAMEL_Z ? `path(evenodd, '${outer} ${scalePath(base, 0.805)}')` : `path('${outer}')`
    const color = depth <= 1 ? enamel : depth === 2 || depth === 6 ? dark : depth >= 9 ? hi : mid
    return { z, style: { clipPath: clip, background: `linear-gradient(100deg, ${hi}, ${color} 32%, ${color} 68%, ${dark})`, transform: `translateZ(${z}px)` } }
  })
})
const progress = computed(() => (props.badge ? progressOf(props.badge) : null))
const multiTier = computed(() => (props.badge?.goals.length || 0) > 1)
const tierIndex = computed(() => TIERS.findIndex(([key]) => key === tier.value))
const earnedThis = computed(() => progress.value && progress.value.earned > (multiTier.value ? tierIndex.value : 0))
const today = () => new Date().toLocaleDateString('zh-TW')
const backTitle = computed(() => (multiTier.value ? `${props.badge?.name} · ${TIERS[tierIndex.value][1]}階` : props.badge?.name || ''))
watch(() => props.badge, () => {
  resetPointer()
  tier.value = 'gold'
  angle.value = 0
})
// 滑鼠位置帶動傾斜與光影，正反面都有反應。
const pointer = reactive({ x: 0.5, y: 0.5 })
const settling = ref(false)
let settleTimer = 0
function settle() {
  settling.value = true
  clearTimeout(settleTimer)
  settleTimer = setTimeout(() => (settling.value = false), 560)
}
const coinStyle = computed(() => ({
  transform: `rotateX(${(0.5 - pointer.y) * 12}deg) rotateY(${angle.value + (pointer.x - 0.5) * 16}deg)`,
  '--spin': `${angle.value * 0.6 + (pointer.x - 0.5) * 130 + (pointer.y - 0.5) * 60}deg`,
  '--hx': `${pointer.x * 100}%`,
  '--hy': `${pointer.y * 100}%`,
}))
const faceGlint = computed(() => angle.value + (pointer.x - 0.5) * 150 + (pointer.y - 0.5) * 70)
function track(event) {
  const box = event.currentTarget.getBoundingClientRect()
  pointer.x = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width))
  pointer.y = Math.min(1, Math.max(0, (event.clientY - box.top) / box.height))
}
function resetPointer() {
  if (dragging.value) return
  pointer.x = 0.5
  pointer.y = 0.5
}
let startX = 0, startAngle = 0, moved = false
function down(event) {
  dragging.value = true
  moved = false
  startX = event.clientX
  startAngle = angle.value
  event.currentTarget.setPointerCapture(event.pointerId)
}
function move(event) {
  track(event)
  if (!dragging.value) return
  const delta = event.clientX - startX
  if (Math.abs(delta) > 3) moved = true
  angle.value = startAngle + delta * 0.8
}
function up() {
  if (!dragging.value) return
  dragging.value = false
  settle()
  angle.value = moved ? Math.round(angle.value / 180) * 180 : startAngle + 180
}
</script>

<template>
  <AppModal :open="Boolean(badge)" :title="badge?.name || ''" modal-class="bd-modal" @close="emit('close')">
    <div v-if="badge" class="bd">
      <div class="bd-stage" :class="{ 'is-drag': dragging, 'is-settling': settling }" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @pointerleave="resetPointer" title="拖曳旋轉，點一下翻面">
        <div :key="tier" class="bd-coin" :class="`is-${tier}`" :style="coinStyle">
          <span v-for="edge in edges" :key="edge.z" class="bd-edge" :style="edge.style"></span>
          <div v-for="[part, z] in [['enamel', ENAMEL_Z], ['art', ART_Z], ['rim', FRONT_Z]]" :key="part" class="bd-face" :style="{ transform: `translateZ(${z}px)` }"><BadgeMedal :badge="badge.id" :shape="badge.shape" :tier="tier" :part="part" :interactive="false" :auto-sheen="part === 'rim'" :glint="faceGlint" /></div>
          <div class="bd-face" :style="{ transform: `rotateY(180deg) translateZ(${-BACK_Z}px)` }"><BadgeMedal :badge="badge.id" :shape="badge.shape" :tier="tier" part="back" :interactive="false" auto-sheen :glint="faceGlint" :back-title="backTitle" :back-date="earnedThis ? today() : '尚未贏得'" /></div>
        </div>
      </div>
      <div v-if="multiTier" class="bd-tiers" role="group" aria-label="切換階級">
        <button v-for="([key, label], i) in TIERS" :key="key" type="button" :class="{ active: tier === key }" @click="tier = key; angle = 0; settle()">
          <BadgeMedal :badge="badge.id" :shape="badge.shape" :tier="key" :interactive="false" /><span>{{ label }} · {{ badge.goals[i] }} {{ badge.unit }}</span>
        </button>
      </div>
      <p class="bd-desc">{{ badge.desc || badge.hint }}</p>
      <p v-if="multiTier" class="bd-progress">目前 {{ progress.value }} {{ badge.unit }}<template v-if="progress.next">，下一階還差 {{ progress.next - progress.value }} {{ badge.unit }}</template></p>
    </div>
  </AppModal>
</template>

<style scoped>
:global(.modal.bd-modal){display:flex;flex-direction:column;overflow:hidden;width:min(440px,calc(100vw - 32px))}
:global(.modal.bd-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none;overflow:auto;padding:6px 24px 18px}
.bd{display:grid;justify-items:center;gap:10px}
.bd-stage{width:240px;height:240px;perspective:900px;filter:drop-shadow(0 10px 14px rgba(40,25,5,.32));cursor:grab;touch-action:none;user-select:none}
.bd-stage.is-drag{cursor:grabbing}
.bd-coin{position:relative;width:240px;height:240px;transform-style:preserve-3d;transition:transform .1s ease-out;animation:bd-in .8s cubic-bezier(.2,.8,.25,1)}
.is-settling .bd-coin{transition:transform .55s cubic-bezier(.2,.8,.25,1)}
.is-drag .bd-coin{transition:none}
.bd-face :deep(.medal){--lx:var(--hx,32%);--ly:var(--hy,22%)}
@keyframes bd-in{from{rotate:y -300deg;scale:.7;opacity:.2}to{rotate:y 0deg;scale:1;opacity:1}}
.bd-edge{position:absolute;inset:0}
.bd-face{position:absolute;inset:0;backface-visibility:hidden;-webkit-backface-visibility:hidden}
.bd-tiers{display:flex;gap:8px}
.bd-tiers button{display:grid;justify-items:center;gap:4px;width:92px;padding:6px 4px;border:1.5px solid transparent;border-radius:12px;background:transparent;color:var(--text);font-size:12px;cursor:pointer}
.bd-tiers button :deep(.medal){width:46px}
.bd-tiers button.active{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 9%,transparent);font-weight:700}
.bd-desc{margin:0;color:var(--text-strong);font-size:15px;font-weight:600;text-align:center}
.bd-progress{margin:0;color:var(--muted);font-size:13px}
@media (prefers-reduced-motion:reduce){.bd-coin{animation:none;transition:none}}
</style>

<script setup>
import { computed, ref } from 'vue'
import BadgeArt from './BadgeArt.vue'
import { METAL, ENAMEL, LOWER, SHAPE_PATHS, scalePath } from './medalShapes.js'
import mark from '@root/assets/pinwise-mark.png'

// 徽章本體：多層金屬外框＋琺瑯面＋掐絲線；銅銀金換材質，細節逐階增加。
const props = defineProps({
  badge: { type: String, default: 'verifier' },
  shape: { type: String, default: 'circle' },
  tier: { type: String, default: 'gold' },
  interactive: { type: Boolean, default: true },
  locked: { type: Boolean, default: false },
  autoSheen: { type: Boolean, default: false },
  glint: { type: Number, default: 0 }, // 外部帶入的光澤角度（翻面時使用）
  part: { type: String, default: 'all' }, // all 完整徽章；rim／enamel／art 是 3D 分層；back 是背面
  backTitle: { type: String, default: '' },
  backDate: { type: String, default: '' },
})
const palette = computed(() => METAL[props.tier] || METAL.gold)
const enamel = computed(() => (props.tier === 'gold' ? ENAMEL[props.badge] || ENAMEL.verifier : LOWER[props.tier]))
const level = computed(() => ['bronze', 'silver', 'gold'].indexOf(props.tier))
const uid = `medal${Math.random().toString(36).slice(2, 9)}`
const base = computed(() => SHAPE_PATHS[props.shape] || SHAPE_PATHS.circle)
const at = (s) => scalePath(base.value, s)
const ring = computed(() => `${at(1)} ${at(0.835)}`)
const hole = (s) => `${at(s)} ${at(0.805)}`
const showRim = computed(() => ['all', 'rim', 'back'].includes(props.part))
const showEnamel = computed(() => ['all', 'enamel'].includes(props.part))
const showArt = computed(() => ['all', 'art'].includes(props.part))
const showOverlays = computed(() => ['all', 'rim', 'back'].includes(props.part))

// 背面拉絲金屬：一圈細楔形依角度明暗變化，旋轉時像金屬在反光。
const hexRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
const mix = (a, b, t) => `rgb(${hexRgb(a).map((v, i) => Math.round(v + (hexRgb(b)[i] - v) * t)).join(',')})`
const brushed = computed(() => {
  const [light, mid, dark] = palette.value.rim
  return Array.from({ length: 120 }, (_, i) => {
    const degree = i * 3, band = (Math.cos((degree * 4 * Math.PI) / 180) + 1) / 2
    const fine = (Math.sin((degree * 23 * Math.PI) / 180) + 1) / 2
    const t = Math.min(1, band * 0.92 + fine * 0.08)
    return { points: wedge(degree - 1.8, degree + 1.8), fill: t < 0.5 ? mix(dark, mid, t * 2) : mix(mid, light, (t - 0.5) * 2) }
  })
})
const ink = computed(() => mix(palette.value.rim[2], '#000000', 0.55))
const stops = (colors) => colors.map((color, i) => ({ color, offset: `${(i / (colors.length - 1)) * 100}%` }))
const polar = (r, degree) => {
  const rad = (degree * Math.PI) / 180
  return [120 + r * Math.cos(rad), 120 + r * Math.sin(rad)]
}
const rays = Array.from({ length: 18 }, (_, i) => {
  const [x1, y1] = polar(170, i * 20 - 4), [x2, y2] = polar(170, i * 20 + 4)
  return `120,120 ${x1},${y1} ${x2},${y2}`
})
const wedge = (from, to) => {
  const [x1, y1] = polar(190, from), [x2, y2] = polar(190, to)
  return `120,120 ${x1},${y1} ${x2},${y2}`
}
const GLINTS = [[wedge(-70, -40), '#fff', 1], [wedge(100, 128), '#fff', 0.9], [wedge(20, 42), '#000', 0.34], [wedge(200, 224), '#000', 0.34]]
const SPARKLES = [[62, 74, 1], [186, 62, 0.8], [196, 170, 0.7]]
const sparkle = ([x, y, k]) => `M${x} ${y - 11 * k}Q${x + k} ${y - k} ${x + 11 * k} ${y}Q${x + k} ${y + k} ${x} ${y + 11 * k}Q${x - k} ${y + k} ${x - 11 * k} ${y}Q${x - k} ${y - k} ${x} ${y - 11 * k}Z`

const root = ref(null)
const pointerGlint = ref(0)
const glintAngle = computed(() => props.glint + pointerGlint.value)
function onMove(event) {
  if (!props.interactive || !root.value) return
  const box = root.value.getBoundingClientRect()
  const x = (event.clientX - box.left) / box.width, y = (event.clientY - box.top) / box.height
  root.value.style.setProperty('--rx', `${(0.5 - y) * 18}deg`)
  root.value.style.setProperty('--ry', `${(x - 0.5) * 18}deg`)
  root.value.style.setProperty('--lx', `${x * 100}%`)
  root.value.style.setProperty('--ly', `${y * 100}%`)
  pointerGlint.value = (x - 0.5) * 150 + (y - 0.5) * 70
}
function onLeave() {
  ;['--rx', '--ry', '--lx', '--ly'].forEach((name) => root.value?.style.removeProperty(name))
  pointerGlint.value = 0
}
</script>

<template>
  <div ref="root" class="medal" :class="[`is-${shape}`, { 'is-layer': part !== 'all', 'is-live': interactive, 'is-locked': locked, 'is-auto': autoSheen }]" @pointermove="onMove" @pointerleave="onLeave">
    <svg viewBox="0 0 240 240" role="img" :aria-label="`${['銅', '銀', '金'][level]}階徽章`">
      <defs>
        <linearGradient :id="`${uid}a`" x1="0" y1="0" x2="1" y2="1"><stop v-for="s in stops(palette.rim)" :key="s.offset" :offset="s.offset" :stop-color="s.color" /></linearGradient>
        <linearGradient :id="`${uid}b`" x1="1" y1="1" x2="0" y2="0"><stop v-for="s in stops(palette.rim)" :key="s.offset" :offset="s.offset" :stop-color="s.color" /></linearGradient>
        <radialGradient :id="`${uid}e`" cx="40%" cy="26%" r="90%"><stop offset="0" :stop-color="enamel[0]" /><stop offset=".52" :stop-color="enamel[1]" /><stop offset="1" :stop-color="enamel[2]" /></radialGradient>
        <linearGradient :id="`${uid}f`" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5A5A62" /><stop offset="1" stop-color="#28282D" /></linearGradient>
        <linearGradient :id="`${uid}j`" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFF8EA" /><stop offset="1" stop-color="#F2D7B2" /></linearGradient>
        <linearGradient :id="`${uid}g`" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".62" /><stop offset="1" stop-color="#fff" stop-opacity="0" /></linearGradient>
        <linearGradient :id="`${uid}l`" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F2FDFF" stop-opacity=".97" /><stop offset="1" stop-color="#9FD8EA" stop-opacity=".78" /></linearGradient>
        <clipPath :id="`${uid}c`"><path :d="at(0.805)" /></clipPath>
        <clipPath :id="`${uid}r`"><path :d="ring" clip-rule="evenodd" /></clipPath>
        <filter :id="`${uid}s`" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7" /></filter>
      </defs>

      <!-- 金屬外框：反向漸層形成斜面，溝線分層 -->
      <g v-if="showRim">
      <path :d="hole(1)" fill-rule="evenodd" :fill="`url(#${uid}a)`" />
      <path :d="at(0.965)" fill="none" stroke="#000" stroke-opacity=".22" stroke-width="1.2" />
      <path :d="hole(0.94)" fill-rule="evenodd" :fill="`url(#${uid}b)`" />
      <path v-if="level < 2" :d="at(0.895)" fill="none" stroke="#000" stroke-opacity=".24" stroke-width="7" stroke-dasharray="1.4 3.8" />
      <template v-else>
        <path :d="at(0.895)" fill="none" stroke="#7E5210" stroke-opacity=".55" stroke-width="7.4" stroke-linecap="round" stroke-dasharray="0 12.6" />
        <path :d="at(0.895)" fill="none" stroke="#FFF9D9" stroke-width="5" stroke-linecap="round" stroke-dasharray="0 12.6" />
      </template>
      <path :d="hole(0.85)" fill-rule="evenodd" :fill="`url(#${uid}a)`" />
      <path :d="hole(0.825)" fill-rule="evenodd" fill="#3A2404" fill-opacity=".55" />

      <!-- 外框光澤：跟著滑鼠或翻轉角度移動 -->
      <g :clip-path="`url(#${uid}r)`"><g :filter="`url(#${uid}s)`" :transform="`rotate(${glintAngle} 120 120)`"><polygon v-for="(item, i) in GLINTS" :key="i" :points="item[0]" :fill="item[1]" :opacity="item[2]" /></g></g>
      </g>

      <!-- 背面：拉絲金屬與刻字 -->
      <g v-if="part === 'back'">
        <g :clip-path="`url(#${uid}c)`">
          <g :transform="`rotate(${glintAngle * 0.7} 120 120)`"><polygon v-for="(w, i) in brushed" :key="i" :points="w.points" :fill="w.fill" /></g>
          <g fill="none" :stroke="ink" stroke-opacity=".13"><circle v-for="r in 16" :key="r" cx="120" cy="120" :r="r * 6.2" stroke-width=".7" /></g>
          <circle cx="120" cy="120" r="82" fill="none" :stroke="ink" stroke-opacity=".5" stroke-width="1.4" />
          <circle cx="120" cy="120" r="83.2" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1" />
          <path d="M20 112A100 100 0 0 1 220 112Q120 62 20 112Z" :fill="`url(#${uid}g)`" opacity=".42" />
        </g>
        <path :id="`${uid}t`" d="M50 124A70 70 0 0 1 190 124" fill="none" />
        <g class="medal-engrave" :fill="ink" text-anchor="middle">
          <text font-size="13" font-weight="700" letter-spacing="3"><textPath :href="`#${uid}t`" startOffset="50%">{{ backTitle }}</textPath></text>
          <image :href="mark" x="104" y="62" width="32" height="32" class="medal-mark" />
          <text x="120" y="116" font-size="12" letter-spacing="3">贏得日期</text>
          <text x="120" y="143" font-size="23" font-weight="800">{{ backDate }}</text>
          <text x="120" y="170" font-size="11" font-weight="800" letter-spacing="5">PINWISE</text>
        </g>
      </g>

      <!-- 琺瑯面 -->
      <g v-if="showEnamel" :clip-path="`url(#${uid}c)`">
        <path :d="at(0.805)" :fill="`url(#${uid}e)`" />
        <polygon v-for="(p, i) in level > 0 ? rays : []" :key="i" :points="p" fill="#fff" opacity=".11" />
        <g v-if="level === 2" fill="none" stroke="#fff" stroke-opacity=".12"><circle v-for="r in 9" :key="r" cx="120" cy="120" :r="r * 11" stroke-width="1" /></g>
      </g>

      <g v-if="showArt" :clip-path="`url(#${uid}c)`">
        <BadgeArt :badge="badge" :uid="uid" :wire="palette.wire" :level="level" />

        <!-- 釉面反光 -->
        <polygon points="30,226 76,226 196,14 150,14" fill="#fff" opacity=".15" />
        <polygon points="90,232 106,232 222,30 206,30" fill="#fff" opacity=".11" />
        <path d="M20 112A100 100 0 0 1 220 112Q120 62 20 112Z" :fill="`url(#${uid}g)`" opacity=".6" />
        <g v-if="level === 2" fill="#fff"><path v-for="(s, i) in SPARKLES" :key="i" class="medal-spark" :style="{ animationDelay: `${i * 0.9}s` }" :d="sparkle(s)" /></g>
      </g>

      <!-- 內線與外框高光 -->
      <path v-if="showRim" :d="at(0.805)" fill="none" stroke="#000" stroke-opacity=".32" stroke-width="1.8" />
      <path v-if="showRim" :d="at(0.992)" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.6" stroke-dasharray="118 620" stroke-dashoffset="-500" stroke-linecap="round" />
    </svg>
    <i v-if="showOverlays" class="medal-light" aria-hidden="true"></i>
    <i v-if="showOverlays" class="medal-sheen" aria-hidden="true"></i>
  </div>
</template>

<style scoped>
.medal{--rx:0deg;--ry:0deg;--lx:32%;--ly:22%;--clip:circle(49.6%);position:relative;width:100%;aspect-ratio:1;transform:perspective(600px) rotateX(var(--rx)) rotateY(var(--ry));transition:transform .18s ease-out;filter:drop-shadow(0 7px 11px rgba(40,25,5,.36))}
.medal.is-hex{--clip:polygon(50% 1%,93% 25.5%,93% 74.5%,50% 99%,7% 74.5%,7% 25.5%)}
.medal.is-shield{--clip:polygon(50% 1%,67% 9%,88% 9.5%,91.5% 14%,91.5% 47%,86% 66%,70% 83%,50% 99%,30% 83%,14% 66%,8.5% 47%,8.5% 14%,12% 9.5%,33% 9%)}
.medal svg{display:block;width:100%;height:100%}
.medal-light,.medal-sheen{position:absolute;inset:0;pointer-events:none;overflow:hidden;clip-path:var(--clip)}
.medal-light{background:radial-gradient(circle at var(--lx) var(--ly),rgba(255,255,255,.62),rgba(255,255,255,0) 46%);mix-blend-mode:soft-light}
.medal-sheen::before{content:'';position:absolute;top:-30%;bottom:-30%;left:-60%;width:38%;background:linear-gradient(100deg,rgba(255,255,255,0),rgba(255,255,255,.8),rgba(255,255,255,0));transform:skewX(-16deg)}
.medal.is-auto .medal-sheen::before{animation:medal-sweep 4.6s ease-in-out infinite}
.medal.is-live:hover .medal-sheen::before{animation:medal-sweep 1.3s ease-in-out}
.medal-spark{transform-box:fill-box;transform-origin:center;animation:medal-twinkle 2.8s ease-in-out infinite}
.medal.is-layer{filter:none;transform:none}
.medal-engrave{filter:drop-shadow(0 .9px 0 rgba(255,255,255,.65))}
.medal-mark{opacity:.8;filter:grayscale(1) contrast(1.5) brightness(.55)}
.medal.is-locked{filter:grayscale(1) brightness(.72) contrast(.9);opacity:.72}
.medal.is-locked .medal-sheen,.medal.is-locked .medal-spark{display:none}
@keyframes medal-sweep{0%,55%{left:-60%}100%{left:125%}}
@keyframes medal-twinkle{0%,100%{opacity:.1;transform:scale(.4)}50%{opacity:1;transform:scale(1)}}
@media (prefers-reduced-motion:reduce){.medal{transition:none}.medal-sheen::before,.medal-spark{animation:none!important}}
</style>

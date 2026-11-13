<script setup>
import { computed } from 'vue'
import Gg from './GgCharacter.vue'

// 每枚徽章的圖騰；座標以 240×240、中心 (120,120) 為準。
const props = defineProps({
  badge: { type: String, required: true },
  uid: { type: String, required: true },
  wire: { type: String, required: true },
  level: { type: Number, default: 2 },
})
const gu = computed(() => `url(#${props.uid}f)`)
const ji = computed(() => `url(#${props.uid}j)`)
const metal = computed(() => `url(#${props.uid}a)`)
const glass = computed(() => `url(#${props.uid}l)`)
const pin = computed(() => props.level === 2)
const PAW_G = '#3A3A40', PAW_J = '#FBE7CC'
</script>

<template>
  <!-- 查證者：放大鏡下的紅漲綠跌 -->
  <g v-if="badge === 'verifier'">
    <Gg transform="translate(-16 4)" :fur="gu" :wire="wire" :pin="pin" />
    <path d="M168 146L156 178" :stroke="metal" stroke-width="10" stroke-linecap="round" />
    <circle cx="154" cy="176" r="11" :fill="PAW_G" :stroke="wire" stroke-width="2.4" />
    <circle cx="175" cy="124" r="23" :fill="glass" />
    <g><rect x="163" y="112" width="2" height="26" fill="#7A2A2A" /><rect x="159" y="118" width="10" height="16" rx="1.5" fill="#E8353F" /><rect x="175" y="106" width="2" height="28" fill="#1C6B4E" /><rect x="171" y="110" width="10" height="18" rx="1.5" fill="#1FB37E" /><rect x="187" y="110" width="2" height="24" fill="#7A2A2A" /><rect x="183" y="114" width="10" height="14" rx="1.5" fill="#E8353F" /></g>
    <path d="M158 116Q168 104 188 106Q176 103 166 106Q160 110 158 116Z" fill="#fff" opacity=".85" />
    <circle cx="175" cy="124" r="24" fill="none" :stroke="metal" stroke-width="6.5" />
  </g>

  <!-- 反方思考家：舉起警告牌 -->
  <g v-else-if="badge === 'contrarian'">
    <Gg transform="translate(-20 6)" :fur="gu" :wire="wire" :pin="pin" eyes="cool" mouth="small" />
    <path d="M176 112V186" :stroke="metal" stroke-width="7" stroke-linecap="round" />
    <path d="M176 66L212 128Q214 133 208 133H144Q138 133 140 128Z" fill="#FFD23F" :stroke="wire" stroke-width="4" stroke-linejoin="round" />
    <path d="M176 78L203 125H149Z" fill="none" stroke="#1A1A1F" stroke-width="3" stroke-linejoin="round" />
    <rect x="172.5" y="91" width="7" height="20" rx="3" fill="#1A1A1F" /><circle cx="176" cy="118" r="4.2" fill="#1A1A1F" />
    <circle cx="170" cy="172" r="11" :fill="PAW_G" :stroke="wire" stroke-width="2.4" />
  </g>

  <!-- 貨比三家：雙人對照兩張走勢卡 -->
  <g v-else-if="badge === 'comparer'">
    <g transform="translate(40 38)"><rect width="66" height="58" rx="8" fill="#fff" :stroke="wire" stroke-width="3.4" /><path d="M8 44L22 30L34 36L58 12" fill="none" stroke="#E8353F" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" /><path d="M58 12H48M58 12V22" fill="none" stroke="#E8353F" stroke-width="4" stroke-linecap="round" /></g>
    <g transform="translate(134 38)"><rect width="66" height="58" rx="8" fill="#fff" :stroke="wire" stroke-width="3.4" /><rect x="10" y="30" width="10" height="20" rx="2" fill="#1FB37E" /><rect x="28" y="20" width="10" height="30" rx="2" fill="#2A78D6" /><rect x="46" y="10" width="10" height="40" rx="2" fill="#FFB020" /></g>
    <Gg transform="translate(3 88) scale(.72)" :fur="gu" :wire="wire" :pin="pin" />
    <Gg transform="translate(64 88) scale(.72)" kind="guji" eyes="bright" :fur="ji" :wire="wire" :pin="pin" />
  </g>

  <!-- ETF 解剖師：一籃子成份股 -->
  <g v-else-if="badge === 'etf'">
    <Gg transform="translate(0 -18)" kind="guji" eyes="bright" mouth="open" :fur="ji" :wire="wire" :pin="pin" />
    <g stroke="#1A1A1F" stroke-width="1.6"><rect x="74" y="138" width="24" height="24" rx="4" fill="#E8353F" transform="rotate(-10 86 150)" /><rect x="102" y="132" width="24" height="24" rx="4" fill="#FFB020" /><rect x="130" y="136" width="24" height="24" rx="4" fill="#1FB37E" transform="rotate(8 142 148)" /><circle cx="162" cy="146" r="12" fill="#2A78D6" transform="translate(-4 2)" /></g>
    <path d="M58 156H182L170 208Q168 214 160 214H80Q72 214 70 208Z" fill="#C98B4B" :stroke="wire" stroke-width="4" stroke-linejoin="round" />
    <path d="M64 172H176M68 190H172M92 158L96 212M120 158V212M148 158L144 212" fill="none" stroke="#7A4E22" stroke-width="2.4" />
    <path d="M58 156H182" :stroke="metal" stroke-width="7" stroke-linecap="round" />
    <circle cx="56" cy="166" r="11" :fill="PAW_J" :stroke="wire" stroke-width="2.4" /><circle cx="184" cy="166" r="11" :fill="PAW_J" :stroke="wire" stroke-width="2.4" />
  </g>

  <!-- 公告偵探：望遠鏡看公告 -->
  <g v-else-if="badge === 'detective'">
    <Gg :fur="gu" :wire="wire" :pin="pin" eyes="sleepy" mouth="small" />
    <g>
      <rect x="74" y="96" width="44" height="42" rx="9" fill="#17171B" :stroke="metal" stroke-width="4" /><rect x="122" y="96" width="44" height="42" rx="9" fill="#17171B" :stroke="metal" stroke-width="4" />
      <rect x="112" y="108" width="16" height="16" rx="3" :fill="metal" />
      <circle cx="96" cy="117" r="15" :fill="glass" :stroke="wire" stroke-width="3.4" /><circle cx="144" cy="117" r="15" :fill="glass" :stroke="wire" stroke-width="3.4" />
      <path d="M86 112Q92 104 102 106M134 112Q140 104 150 106" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" />
      <circle cx="70" cy="140" r="11" :fill="PAW_G" :stroke="wire" stroke-width="2.4" /><circle cx="170" cy="140" r="11" :fill="PAW_G" :stroke="wire" stroke-width="2.4" />
    </g>
    <g transform="rotate(10 184 186)"><rect x="162" y="160" width="44" height="52" rx="4" fill="#FFFDF3" :stroke="wire" stroke-width="3" /><path d="M170 172H198M170 182H198M170 192H188" stroke="#7A8393" stroke-width="3" stroke-linecap="round" /><circle cx="196" cy="202" r="7" fill="#E3212E" /></g>
  </g>

  <!-- 風險守門人：舉盾擋風險 -->
  <g v-else-if="badge === 'guardian'">
    <Gg transform="translate(-22 6)" :fur="gu" :wire="wire" :pin="pin" />
    <path d="M172 84Q190 94 212 92V136Q212 174 172 196Q132 174 132 136V92Q154 94 172 84Z" :fill="metal" :stroke="wire" stroke-width="2.4" />
    <path d="M172 97Q187 104 202 103V136Q202 166 172 184Q142 166 142 136V103Q157 104 172 97Z" fill="#C8243A" />
    <path d="M154 138L168 153L192 122" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M148 110Q172 100 196 110L148 150Z" fill="#fff" opacity=".2" />
    <circle cx="138" cy="176" r="11" :fill="PAW_G" :stroke="wire" stroke-width="2.4" />
  </g>

  <!-- 回饋夥伴：比讚與愛心 -->
  <g v-else-if="badge === 'partner'">
    <Gg transform="translate(-18 6)" kind="guji" eyes="happy" mouth="open" :fur="ji" :wire="wire" :pin="pin" />
    <path d="M144 46H204Q214 46 214 56V92Q214 102 204 102H172L156 116L158 102H144Q134 102 134 92V56Q134 46 144 46Z" fill="#fff" :stroke="wire" stroke-width="3.6" stroke-linejoin="round" />
    <path d="M174 92Q150 76 156 64Q163 54 174 66Q185 54 192 64Q198 76 174 92Z" fill="#E8354F" /><path d="M160 66Q163 60 169 64" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" />
    <g transform="translate(150 132)"><path d="M6 26Q6 18 14 16L20 2Q24 -4 28 2Q30 8 26 16H42Q50 18 46 28L40 48Q38 54 30 54H12Q6 54 6 48Z" :fill="PAW_J" :stroke="wire" stroke-width="3.2" stroke-linejoin="round" /></g>
  </g>

  <!-- 定期回顧：抱著打勾的週曆 -->
  <g v-else-if="badge === 'streak'">
    <Gg transform="translate(0 -22)" kind="guji" eyes="bright" :fur="ji" :wire="wire" :pin="pin" />
    <rect x="66" y="134" width="108" height="82" rx="10" fill="#FFFDF3" :stroke="wire" stroke-width="4" />
    <path d="M66 156V144Q66 134 76 134H164Q174 134 174 144V156Z" fill="#E3212E" />
    <path d="M90 126V144M150 126V144" :stroke="metal" stroke-width="7" stroke-linecap="round" />
    <g fill="#CFE9D9"><circle v-for="i in 5" :key="i" :cx="62 + i * 19.6" cy="172" r="7" /></g>
    <g fill="none" stroke="#12A66E" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path v-for="i in 4" :key="i" :d="`M${58 + i * 19.6} 172l3 3.5l6 -7`" /></g>
    <g fill="#E7EBF0"><circle v-for="i in 5" :key="i" :cx="62 + i * 19.6" cy="196" r="7" /></g>
    <circle cx="58" cy="182" r="11" :fill="PAW_J" :stroke="wire" stroke-width="2.4" /><circle cx="182" cy="182" r="11" :fill="PAW_J" :stroke="wire" stroke-width="2.4" />
  </g>

  <!-- 隱藏：分割偵探（紅綠箭頭眼，股市情境特效） -->
  <g v-else-if="badge === 'split'">
    <Gg transform="translate(-22 10)" eyes="arrow" mouth="small" :fur="gu" :wire="wire" :pin="pin" />
    <rect x="166" y="52" width="4" height="150" rx="2" fill="#7A2A2A" />
    <rect x="152" y="66" width="32" height="46" rx="4" fill="#E8353F" :stroke="wire" stroke-width="3" /><rect x="152" y="134" width="32" height="46" rx="4" fill="#E8353F" :stroke="wire" stroke-width="3" transform="translate(6 8)" />
    <path d="M144 124L204 118" stroke="#fff" stroke-width="2.4" stroke-dasharray="5 4" />
    <g transform="translate(196 124) rotate(172)"><path d="M0 0L42 -12M0 0L42 12" :stroke="metal" stroke-width="6" stroke-linecap="round" /><circle cx="50" cy="-15" r="8.5" fill="none" :stroke="metal" stroke-width="5" /><circle cx="50" cy="15" r="8.5" fill="none" :stroke="metal" stroke-width="5" /></g>
  </g>

  <!-- 隱藏：先停一下 -->
  <g v-else-if="badge === 'pause'">
    <path d="M150 196L196 74M196 74L168 86M196 74L208 102" fill="none" stroke="#E8353F" stroke-width="11" stroke-linecap="round" stroke-linejoin="round" opacity=".78" />
    <Gg transform="translate(-24 8)" eyes="cool" mouth="small" :fur="gu" :wire="wire" :pin="pin" />
    <g transform="translate(120 96)"><circle cx="46" cy="44" r="27" :fill="PAW_G" :stroke="wire" stroke-width="3.4" /><g :stroke="wire" stroke-width="2.6" :fill="PAW_G"><ellipse cx="24" cy="22" rx="8.5" ry="11" /><ellipse cx="42" cy="12" rx="8.5" ry="11" /><ellipse cx="60" cy="14" rx="8.5" ry="11" /><ellipse cx="74" cy="28" rx="8" ry="10.5" /></g><ellipse cx="46" cy="48" rx="13" ry="11" fill="#F4A9B8" /><circle cx="28" cy="24" r="4" fill="#F4A9B8" /><circle cx="42" cy="14" r="4" fill="#F4A9B8" /><circle cx="60" cy="16" r="4" fill="#F4A9B8" /><circle cx="72" cy="29" r="3.6" fill="#F4A9B8" /></g>
  </g>

  <!-- 隱藏：敢說真話 -->
  <g v-else-if="badge === 'honest'">
    <Gg transform="translate(-18 8)" kind="guji" eyes="bright" mouth="open" :fur="ji" :wire="wire" :pin="pin" />
    <path d="M146 40H204Q214 40 214 50V88Q214 98 204 98H178L162 112L164 98H146Q136 98 136 88V50Q136 40 146 40Z" fill="#fff" :stroke="wire" stroke-width="3.6" stroke-linejoin="round" />
    <rect x="170.5" y="50" width="9" height="28" rx="4.5" fill="#E3212E" /><circle cx="175" cy="88" r="5" fill="#E3212E" />
    <g transform="rotate(16 170 164)"><path d="M170 172V202" :stroke="metal" stroke-width="8" stroke-linecap="round" /><rect x="154" y="132" width="32" height="44" rx="16" :fill="metal" :stroke="wire" stroke-width="2" /><path d="M156 148H184M156 158H184" stroke="#7E5210" stroke-width="2" /><path d="M162 138Q166 134 172 136" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" /></g>
    <circle cx="160" cy="190" r="11" :fill="PAW_J" :stroke="wire" stroke-width="2.4" />
  </g>

  <!-- 隱藏：收盤研究員 -->
  <g v-else-if="badge === 'night'">
    <path d="M188 40A32 32 0 1 0 212 92A26 26 0 0 1 188 40Z" :fill="metal" :stroke="wire" stroke-width="1.6" />
    <g fill="#FFF6C9"><path d="M150 52l2.4 6.6l6.6 2.4l-6.6 2.4l-2.4 6.6l-2.4-6.6l-6.6-2.4l6.6-2.4Z" /><path d="M60 66l1.8 4.8l4.8 1.8l-4.8 1.8l-1.8 4.8l-1.8-4.8l-4.8-1.8l4.8-1.8Z" /></g>
    <Gg transform="translate(-22 10)" eyes="sleepy" :fur="gu" :wire="wire" :pin="pin" />
    <g><path d="M186 142V186Q186 196 176 196H150Q140 196 140 186V142Z" fill="#FFFDF3" :stroke="wire" stroke-width="3.6" /><path d="M186 152H194Q204 152 204 164Q204 176 194 176H186" fill="none" :stroke="wire" stroke-width="5" /><path d="M140 150H186V156H140Z" fill="#7A4E22" /><path d="M153 134Q147 126 153 118M171 134Q165 126 171 118" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".85" /></g>
    <circle cx="140" cy="182" r="11" :fill="PAW_G" :stroke="wire" stroke-width="2.4" />
  </g>

  <!-- 隱藏：看穿重疊 -->
  <g v-else-if="badge === 'overlap'">
    <circle cx="94" cy="86" r="44" fill="#E8353F" fill-opacity=".82" :stroke="wire" stroke-width="3.6" /><circle cx="146" cy="86" r="44" fill="#2A78D6" fill-opacity=".82" :stroke="wire" stroke-width="3.6" />
    <path d="M120 51A44 44 0 0 1 120 121A44 44 0 0 1 120 51Z" :fill="metal" :stroke="wire" stroke-width="2" />
    <path d="M120 66V106M112 74H128M112 98H128" stroke="#7E5210" stroke-width="3" stroke-linecap="round" />
    <Gg transform="translate(36 96) scale(.7)" kind="guji" eyes="bright" mouth="open" :fur="ji" :wire="wire" :pin="pin" />
  </g>

  <!-- 隱藏：走到那條線（目標達成） -->
  <g v-else>
    <g><rect x="44" y="34" width="5" height="122" rx="2" :fill="metal" /><rect x="191" y="34" width="5" height="122" rx="2" :fill="metal" />
      <path d="M49 54H191V82H49Z" fill="#fff" :stroke="wire" stroke-width="3" />
      <g fill="#1A1A1F"><template v-for="c in 10" :key="c"><rect :x="49 + (c - 1) * 14.2" :y="c % 2 ? 54 : 68" width="14.2" height="14" /></template></g>
    </g>
    <path d="M48 158Q120 142 192 158" fill="none" stroke="#FFD23F" stroke-width="6" stroke-linecap="round" />
    <Gg transform="translate(14 98) scale(.66)" eyes="happy" :fur="gu" :wire="wire" :pin="pin" />
    <Gg transform="translate(68 98) scale(.66)" kind="guji" eyes="happy" mouth="open" :fur="ji" :wire="wire" :pin="pin" />
    <g fill="#FFF6C9"><path d="M72 92l2 5.6l5.6 2l-5.6 2l-2 5.6l-2-5.6l-5.6-2l5.6-2Z" /><path d="M170 96l2 5.6l5.6 2l-5.6 2l-2 5.6l-2-5.6l-5.6-2l5.6-2Z" /></g>
  </g>
</template>

<script setup>
// 股怪、股吉的徽章造型：依素材包定稿，同族 Q 版、大頭小身、粉色內耳、黑西裝白襯衫紅領帶。
// eyes：cool 半瞇略跩、bright 明亮、happy 笑瞇、arrow 紅漲綠跌（只用於股市情境的隱藏徽章）、sleepy 收盤。
defineProps({
  kind: { type: String, default: 'guguai' },
  eyes: { type: String, default: 'cool' },
  fur: { type: String, required: true },
  wire: { type: String, required: true },
  pin: { type: Boolean, default: false },
  mouth: { type: String, default: 'cat' }, // cat | open | small
})
const HEAD = {
  guguai: 'M70 96L60 50Q58 42 66 46L96 68Q104 64 110 66L114 50L122 65L131 52L134 67Q140 65 146 68L174 46Q182 42 180 50L170 96Q178 108 176 122L186 128L173 134L177 148L162 145Q144 162 120 162Q96 162 78 145L63 148L67 134L54 128L64 122Q62 108 70 96Z',
  guji: 'M70 96L62 54Q60 46 68 49L97 69Q106 64 112 66L108 50L120 62L132 48L129 66Q135 65 143 69L172 49Q180 46 178 54L170 96Q180 108 177 124L186 131L174 136L175 148L162 146Q144 162 120 162Q96 162 78 146L65 148L66 136L54 131L63 124Q60 108 70 96Z',
}
</script>

<template>
  <g stroke-linejoin="round">
    <path d="M82 212Q80 166 104 156L120 170L136 156Q160 166 158 212Z" fill="#1A1A1F" :stroke="wire" stroke-width="2.6" />
    <path d="M90 212Q90 178 106 162M150 212Q150 178 134 162" fill="none" stroke="#fff" stroke-opacity=".16" stroke-width="2" />
    <path d="M106 157L120 180L134 157Z" fill="#fff" />
    <path d="M116 162H124L122 170L129 200L120 212L111 200L118 170Z" fill="#E3212E" :stroke="wire" stroke-width="1.4" />
    <path d="M117 172L119 196" stroke="#fff" stroke-opacity=".4" stroke-width="1.6" stroke-linecap="round" />
    <rect v-if="pin" x="113" y="186" width="14" height="3.4" rx="1.5" :fill="wire" />
    <path :d="HEAD[kind]" :fill="fur" :stroke="wire" stroke-width="3.2" />
    <path d="M73 86L69 59L91 73Q79 77 73 86ZM167 86L171 59L149 73Q161 77 167 86Z" fill="#F4A9B8" />
    <ellipse cx="116" cy="84" rx="38" ry="15" fill="#fff" :opacity="kind === 'guji' ? .5 : .14" />
    <path d="M92 76l-3-7M106 72l-2-8M132 72l2-8M148 76l3-7M66 138l-7 2M70 124l-6-3M174 138l7 2M170 124l6-3" fill="none" :stroke="kind === 'guji' ? '#D9BC95' : '#6A6A72'" stroke-width="2" stroke-linecap="round" />
    <ellipse cx="84" cy="131" rx="10" ry="5.5" fill="#F4A9B8" :opacity="kind === 'guji' ? .75 : .35" /><ellipse cx="156" cy="131" rx="10" ry="5.5" fill="#F4A9B8" :opacity="kind === 'guji' ? .75 : .35" />

    <template v-if="eyes === 'cool'">
      <ellipse cx="98" cy="113" rx="15" ry="13.5" fill="#fff" /><ellipse cx="142" cy="113" rx="15" ry="13.5" fill="#fff" />
      <circle cx="103" cy="115" r="9.5" fill="#111" /><circle cx="147" cy="115" r="9.5" fill="#111" />
      <circle cx="106.5" cy="111" r="3" fill="#fff" /><circle cx="150.5" cy="111" r="3" fill="#fff" />
      <path d="M80 110Q98 94 116 106L116 94L80 94ZM124 106Q142 94 160 110L160 94L124 94Z" fill="#46464D" />
      <path d="M82 109Q98 98 115 105M125 105Q142 98 158 109" fill="none" stroke="#111" stroke-width="3" stroke-linecap="round" />
    </template>
    <template v-else-if="eyes === 'bright'">
      <ellipse cx="98" cy="113" rx="15" ry="16" fill="#111" /><ellipse cx="142" cy="113" rx="15" ry="16" fill="#111" />
      <circle cx="103" cy="106" r="5.4" fill="#fff" /><circle cx="147" cy="106" r="5.4" fill="#fff" />
      <circle cx="93" cy="119" r="2.6" fill="#fff" /><circle cx="137" cy="119" r="2.6" fill="#fff" />
    </template>
    <template v-else-if="eyes === 'happy'">
      <path d="M84 117Q98 98 112 117M128 117Q142 98 156 117" fill="none" stroke="#111" stroke-width="5" stroke-linecap="round" />
    </template>
    <template v-else-if="eyes === 'sleepy'">
      <path d="M84 112Q98 122 112 112M128 112Q142 122 156 112" fill="none" stroke="#111" stroke-width="4.4" stroke-linecap="round" />
    </template>
    <template v-else>
      <ellipse cx="98" cy="113" rx="15" ry="14" fill="#fff" stroke="#111" stroke-width="2" /><ellipse cx="142" cy="113" rx="15" ry="14" fill="#fff" stroke="#111" stroke-width="2" />
      <circle cx="98" cy="113" r="10.5" fill="#E8212E" /><circle cx="142" cy="113" r="10.5" fill="#12A66E" />
      <path d="M98 105L104 113H100V120H96V113H92Z" fill="#fff" /><path d="M142 121L148 113H144V106H140V113H136Z" fill="#fff" />
    </template>

    <path v-if="mouth === 'cat'" d="M111 138Q115.5 145 120 138Q124.5 145 129 138" fill="none" :stroke="kind === 'guji' ? '#7A4A3A' : '#141418'" stroke-width="2.6" stroke-linecap="round" />
    <path v-else-if="mouth === 'open'" d="M108 135Q120 133 132 135Q131 153 120 153Q109 153 108 135Z" fill="#E8596E" stroke="#7A2A3A" stroke-width="2" />
    <path v-else d="M114 140H126" :stroke="kind === 'guji' ? '#7A4A3A' : '#141418'" stroke-width="2.8" stroke-linecap="round" />
    <path v-if="kind === 'guji' || mouth === 'cat'" d="M117.5 133L120 135.5L122.5 133Z" :fill="kind === 'guji' ? '#E58A9A' : '#141418'" />
  </g>
</template>

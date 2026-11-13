<script setup>
import AppDrawer from '@/components/AppDrawer.vue'
import AppIcon from '@/components/AppIcon.vue'
import { featureGuides } from '@/data/tours.js'
import { overlays } from '@/stores/overlays.js'
import { useRoute } from 'vue-router'
import { startTour } from '@/stores/tour.js'

// 功能教學：選一個頁面，前往並啟動該頁的互動導覽。
// 教學結束（完成、跳過或按 Esc）後回到原本的頁面，並重新打開這個抽屜，方便接著看下一個。
const route = useRoute()
function start(page) {
  overlays.featureGuide = false
  startTour(page, { restore: true, currentPath: route.fullPath, onEnd: () => (overlays.featureGuide = true) })
}
</script>

<template>
  <AppDrawer :open="overlays.featureGuide" title="功能教學" eyebrow="教學與幫助" size="medium" @close="overlays.featureGuide = false">
    <div class="feature-guide-intro">選擇一個頁面後，PINWISE 會直接前往該頁並啟動專屬互動教學。</div>
    <div class="feature-guide-list">
      <button v-for="[page, icon, title, desc] in featureGuides" :key="page" type="button" @click="start(page)">
        <span><AppIcon :name="icon" :size="19" /></span>
        <div><strong>{{ title }}</strong><small>{{ desc }}</small></div>
        <em>開始教學 →</em>
      </button>
    </div>
  </AppDrawer>
</template>

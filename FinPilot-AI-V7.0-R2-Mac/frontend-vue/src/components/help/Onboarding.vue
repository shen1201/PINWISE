<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppModal from '@/components/AppModal.vue'
import AppIcon from '@/components/AppIcon.vue'
import PreferenceForm from '@/components/PreferenceForm.vue'
import { settings, toast } from '@/stores/ui.js'
import { overlays } from '@/stores/overlays.js'
import { startTour } from '@/stores/tour.js'
import { tours } from '@/data/tours.js'
import { PREFERENCE_QUESTIONS } from '@/data/preferences.js'

// 與學習專區「新手起步」同一條路線。
const FLOW = [
  ['找標的', '智慧選股用一句話列出候選與列入原因'],
  ['深入了解', 'AI 標的研究整理理由、風險與來源'],
  ['放在一起看', '股票比較用同一組標準對照'],
  ['持續留意', '加入追蹤，回來看表現與公告'],
]
const tourNames = tours.full.map((s) => s.title.replace(/^\d+\.\s*/, '').split('｜')[0]).join('、')

// 首次使用流程：歡迎 → 個人偏好問卷 → 詢問是否看導覽（對應舊版 showWelcomeOnboarding 等）。
const route = useRoute()
const step = computed(() => overlays.onboarding)
const title = computed(() => ({ welcome: '歡迎使用 PINWISE', preferences: '建立個人化偏好', tourOffer: '要先看簡短導覽嗎？' })[step.value] || '')
const modalClass = computed(() => (step.value === 'tourOffer' ? 'compact-action-modal' : step.value === 'preferences' ? ['onboarding-modal', 'preference-modal'] : 'onboarding-modal'))

function skipAll(message) {
  settings.onboardingCompleted = true
  toast(message)
  overlays.onboarding = 'tourOffer'
}
function prefsSaved() {
  settings.onboardingCompleted = true
  overlays.onboarding = 'tourOffer'
}
function startFullTour() {
  overlays.onboarding = null
  startTour('full', { restore: true, currentPath: route.fullPath })
}
// 歡迎與問卷必須選擇一個按鈕才能離開（不顯示 ✕）；只有導覽詢問可以直接關閉。
const closable = computed(() => step.value === 'tourOffer')
const close = () => closable.value && (overlays.onboarding = null)
</script>

<template>
  <AppModal :open="Boolean(step)" :title="title" :modal-class="modalClass" :closable="closable" @close="close">
    <div v-if="step === 'welcome'" class="welcome-onboarding">
      <div class="welcome-mark"><AppIcon name="compass" :size="28" /></div>
      <h3>先用一分鐘認識 PINWISE</h3>
      <p>數字都由程式從官方資料計算，AI 負責理解問題和用白話說明，不替你做買賣決定。看不懂的地方，隨時問左下角的 PINWISE 助手。</p>
      <div class="welcome-steps ob-steps">
        <section v-for="([title, desc], i) in FLOW" :key="title"><b>{{ i + 1 }}</b><div><strong>{{ title }}</strong><span>{{ desc }}</span></div></section>
      </div>
      <div class="welcome-personalize">
        <strong>要先建立個人偏好嗎？</strong>
        <span>完成後，AI 能用更符合你的解釋深度、觀察期間與風險承受方式回答。</span>
      </div>
      <div class="candidate-dialog-actions">
        <button class="outline-button" type="button" @click="skipAll('之後可從設定建立投資偏好')">暫時略過</button>
        <button class="primary-button" type="button" @click="overlays.onboarding = 'preferences'">開始設定</button>
      </div>
    </div>

    <template v-else-if="step === 'preferences'">
      <div class="preference-onboarding-intro"><p>{{ PREFERENCE_QUESTIONS.length }} 個簡單選項，之後也能在設定中修改。</p></div>
      <PreferenceForm context="onboarding" @saved="prefsSaved" @skip="skipAll('已略過，這次會採一般分析')" />
    </template>

    <div v-else-if="step === 'tourOffer'" class="tour-offer">
      <p>共 {{ tours.full.length }} 步，約一分鐘：{{ tourNames }}。之後也能在學習專區重新開啟。</p>
      <div class="candidate-dialog-actions">
        <button class="outline-button" type="button" @click="overlays.onboarding = null">先自己看看</button>
        <button class="primary-button" type="button" @click="startFullTour">開始導覽</button>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.ob-steps{grid-template-columns:repeat(4,minmax(0,1fr))}
@media (max-width:620px){.ob-steps{grid-template-columns:1fr 1fr}}
/* 筆電高度（約 720px）時問卷要一次看完，按鈕不被視窗切掉 */
@media (min-width:621px) and (max-height:820px){
  :global(.modal.onboarding-modal.preference-modal){transform:translate(-50%,-50%)!important}
  :global(.preference-form[data-context="onboarding"]){gap:6px;margin-top:6px}
  :global(.preference-form[data-context="onboarding"] .preference-question){padding:4px 12px 7px}
  :global(.preference-form[data-context="onboarding"] .preference-options){margin-top:4px}
  :global(.preference-form[data-context="onboarding"] .preference-options label span){min-height:30px;padding:4px 9px}
  :global(.preference-onboarding-intro p){margin:0}
}
</style>

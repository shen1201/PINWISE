<script setup>
import { reactive } from 'vue'
import { settings, toast } from '@/stores/ui.js'
import { PREFERENCE_QUESTIONS as QUESTIONS } from '@/data/preferences.js'

// 個人化偏好問卷（對應舊版 preferenceQuestionnaireHtml / savePreferenceForm）；設定頁與首次使用共用。
const props = defineProps({ context: { type: String, default: 'settings' } }) // settings | onboarding
const emit = defineEmits(['saved', 'skip'])

const answers = reactive(Object.fromEntries(QUESTIONS.map(([key]) => [key, settings.personalPrefs[key] || ''])))

function save() {
  const missing = QUESTIONS.find(([key]) => !answers[key])
  if (missing) return toast('請完成所有偏好選項')
  Object.assign(settings.personalPrefs, answers, { completed: true, updatedAt: new Date().toISOString() })
  toast(props.context === 'onboarding' ? '已完成個人化偏好設定' : '已更新個人化偏好')
  emit('saved')
}
</script>

<template>
  <form class="preference-form" :data-context="context" @submit.prevent="save">
    <fieldset v-for="([key, label, options], index) in QUESTIONS" :key="key" class="preference-question">
      <legend><span>{{ index + 1 }}</span>{{ label }}</legend>
      <div class="preference-options" :class="{ 'is-wide': options.length > 4 }">
        <label v-for="value in options" :key="value">
          <input v-model="answers[key]" type="radio" :name="`pref-${key}`" :value="value" /><span>{{ value }}</span>
        </label>
      </div>
    </fieldset>
    <div class="preference-form-actions">
      <button v-if="context === 'onboarding'" class="outline-button" type="button" @click="emit('skip')">暫時略過</button>
      <button class="primary-button" type="submit">{{ settings.personalPrefs.completed ? '更新偏好' : '儲存偏好' }}</button>
    </div>
  </form>
</template>

<style scoped>
/* 5 個選項（預估投入）排成一列 */
@media (min-width:901px){.preference-options.is-wide{grid-template-columns:repeat(5,minmax(0,1fr))}}
</style>

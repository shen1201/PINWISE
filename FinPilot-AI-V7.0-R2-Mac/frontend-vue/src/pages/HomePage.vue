<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import { topicQueries } from '@/data/nav.js'
import { recentTasks, beginResearch } from '@/stores/research.js'
import { workspace } from '@/stores/workspace.js'

const router = useRouter()
const query = ref('')
const hint = ref('')
const inputEl = ref(null)
const submitting = ref(false)

const topics = ['熱門主題', 'AI 概念股', '高股息 ETF', '電動車產業', '生技醫療', '自訂主題']

// 先由後端理解輸入；能直接建立研究就前往研究頁，否則由 ResearchDialogs 顯示確認視窗。
async function submit() {
  const q = query.value.trim()
  if (!q) {
    hint.value = '請先輸入想研究的問題。'
    inputEl.value?.focus()
    return
  }
  hint.value = ''
  submitting.value = true
  try {
    if (await beginResearch(q, 'home')) router.push('/research')
  } finally {
    submitting.value = false
  }
}

// 主題範例填進上方輸入框（不直接送出），按「開始 AI 研究」才前往 AI 標的研究；「自訂主題」清空讓使用者自己輸入。
function pickTopic(topic) {
  query.value = topicQueries[topic] || ''
  hint.value = ''
  inputEl.value?.focus()
}
</script>

<template>
  <div class="home-page">
    <section class="home-hero">
      <div class="home-content">
        <h1 class="home-title">今天想讓 <em>AI</em> 幫你研究什麼？</h1>
        <p class="home-subtitle">不管你是新手還是老手，PINWISE 都會用最簡單的方式陪你找到好標的。</p>
        <form class="hero-query" @submit.prevent="submit">
          <input
            id="homeResearchInput"
            ref="inputEl"
            v-model="query"
            placeholder="輸入一檔股票或 ETF，例如：2330、台積電的成長與風險、0050"
            autocomplete="off"
            aria-label="正式 AI 研究問題"
            aria-describedby="homeResearchHint"
            :aria-invalid="hint ? 'true' : undefined"
          />
          <button type="submit" aria-label="開始正式 AI 研究" :disabled="submitting">
            <AppIcon name="search" :size="18" /><span>{{ submitting ? '理解中…' : '開始 AI 研究' }}</span>
          </button>
        </form>
        <small id="homeResearchHint" class="home-demo-note is-error" role="status" :hidden="!hint">{{ hint }}</small>
        <!-- 保留這一行的高度，下方版面位置不變 -->
        <div class="research-input-guide" aria-hidden="true">&nbsp;</div>
        <div class="topic-row">
          <button v-for="topic in topics" :key="topic" class="topic-chip" type="button" @click="pickTopic(topic)">{{ topic }}</button>
        </div>
      </div>
      <div class="home-summary">
        <article class="summary-card surface-glass is-action" role="button" tabindex="0" @click="router.push('/candidates')" @keydown.enter="router.push('/candidates')">
          <div>
            <h3><span class="inline-icon"><AppIcon name="star" :size="18" /></span>我的追蹤</h3>
            <div class="summary-number">{{ workspace.tracked.length }} 檔</div>
            <small>點入查看表現與波動</small>
          </div>
          <div class="summary-icon"><AppIcon name="star" :size="25" /></div>
        </article>
        <article class="summary-card surface-glass is-action" role="button" tabindex="0" @click="router.push('/research')" @keydown.enter="router.push('/research')">
          <div>
            <h3><span class="inline-icon"><AppIcon name="database" :size="18" /></span>最近研究紀錄</h3>
            <div class="summary-number">{{ recentTasks.length }} 份</div>
            <small>近七天建立的研究</small>
          </div>
          <div class="summary-icon"><AppIcon name="database" :size="25" /></div>
        </article>
      </div>
    </section>
  </div>
</template>

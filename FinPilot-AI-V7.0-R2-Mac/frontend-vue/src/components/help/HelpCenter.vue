<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppModal from '@/components/AppModal.vue'
import { faqs, glossary, GLOSSARY_GROUPS } from '@/data/learning.js'
import { articles } from '@/data/articles.js'
import { overlays, openHelp } from '@/stores/overlays.js'

// 幫助中心：常見問題、投資名詞與閱讀指南。名詞依分類篩選，並可直接前往網站上看得到它的頁面。
const router = useRouter()
const help = computed(() => overlays.help)
const category = ref('熱門問題')
const group = ref('全部')
const query = ref('')
const openFaq = ref(-1)

watch(() => help.value && [help.value.tab, help.value.term], () => {
  category.value = help.value?.tab === 'faq' ? '熱門問題' : '全部'
  group.value = '全部'
  // 從其他地方點名詞（openTerm）時，直接用該名詞搜尋。
  query.value = help.value?.term || ''
  openFaq.value = -1
})

const categories = ['熱門問題', '全部', ...new Set(faqs.map((x) => x[2]).filter((x) => x !== '熱門問題'))]
const groups = ['全部', ...GLOSSARY_GROUPS]
const q = computed(() => query.value.trim().toLowerCase())
const faqItems = computed(() =>
  faqs.filter(([question, answer, cat, hot]) =>
    (category.value === '全部' || (category.value === '熱門問題' && hot) || cat === category.value) &&
    (!q.value || (question + answer + cat).toLowerCase().includes(q.value)),
  ),
)
const glossaryItems = computed(() =>
  glossary.filter(([term, text, cat]) => (group.value === '全部' || cat === group.value) && (!q.value || (term + text).toLowerCase().includes(q.value))),
)
const isFaq = computed(() => help.value?.tab === 'faq')

function goTo(path) {
  overlays.help = null
  router.push(path)
}

const article = computed(() => articles[help.value?.article])
const title = computed(() => (article.value ? article.value.title : '幫助中心'))
const modalClass = computed(() => (article.value ? 'learning-article-modal' : 'help-center-modal'))
</script>

<template>
  <AppModal :open="Boolean(help)" :title="title" :modal-class="modalClass" @close="overlays.help = null">
    <!-- 閱讀指南 -->
    <div v-if="article" class="learning-article-content">
      <span class="eyebrow">學習專區 · 閱讀指南</span>
      <p class="learning-article-lead">{{ article.intro }}</p>
      <div class="learning-article-sections">
        <section v-for="([heading, body], i) in article.sections" :key="heading">
          <b>{{ i + 1 }}</b>
          <div><h3>{{ heading }}</h3><p>{{ body }}</p></div>
        </section>
      </div>
    </div>

    <!-- 常見問題／投資名詞 -->
    <div v-else-if="help" class="help-center hc">
      <div class="help-center-tabs" role="tablist">
        <button type="button" role="tab" :aria-selected="String(isFaq)" :class="{ active: isFaq }" @click="openHelp('faq')">常見問題</button>
        <button type="button" role="tab" :aria-selected="String(!isFaq)" :class="{ active: !isFaq }" @click="openHelp('glossary')">投資名詞</button>
      </div>
      <label class="help-center-search">
        <span>{{ isFaq ? '搜尋問題' : '搜尋名詞' }}</span>
        <input v-model="query" type="search" :placeholder="isFaq ? '例如：研究進度、追蹤、成份股' : '例如：本益比、回撤、ETF'" />
      </label>
      <div class="faq-categories hc-cats">
        <template v-if="isFaq"><button v-for="c in categories" :key="c" type="button" :class="{ active: category === c }" @click="category = c">{{ c }}</button></template>
        <template v-else><button v-for="g in groups" :key="g" type="button" :class="{ active: group === g }" @click="group = g">{{ g }}</button></template>
      </div>
      <div class="help-center-summary">
        <strong>{{ isFaq ? faqItems.length : glossaryItems.length }}</strong> 個{{ isFaq ? '問題' : '名詞' }}
        <span v-if="!(isFaq ? faqItems : glossaryItems).length">試試「研究」、「風險」或「回撤」</span>
      </div>
      <div class="help-center-results">
        <template v-if="isFaq">
          <div v-for="([question, answer, cat], i) in faqItems" :key="question" class="faq-row" :class="{ open: openFaq === i }" :data-faq-category="cat">
            <button type="button" class="faq-toggle" :aria-expanded="String(openFaq === i)" @click="openFaq = openFaq === i ? -1 : i">
              <span>{{ question }}</span><b aria-hidden="true">{{ openFaq === i ? '－' : '＋' }}</b>
            </button>
            <div class="faq-answer" :hidden="openFaq !== i"><div>{{ answer }}</div></div>
          </div>
          <div v-if="!faqItems.length" class="empty-state">找不到符合的問題。</div>
        </template>
        <template v-else>
          <div class="hc-grid">
            <article v-for="[name, text, cat, where] in glossaryItems" :key="name" class="glossary-item hc-term">
              <header><strong>{{ name }}</strong><small>{{ cat }}</small></header>
              <p>{{ text }}</p>
              <button v-if="where" class="card-link" type="button" @click="goTo(where[1])">到「{{ where[0] }}」看 →</button>
            </article>
          </div>
          <div v-if="!glossaryItems.length" class="empty-state">找不到符合的名詞。</div>
        </template>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.hc{grid-template-rows:auto auto auto auto minmax(0,1fr)!important}
.hc-cats{margin:0!important}
.hc-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding-top:10px}
.hc-term{display:flex;flex-direction:column;gap:4px;margin:0}
.hc-term header{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.hc-term header small{flex:none;color:var(--muted);font-size:12px}
.hc-term p{flex:1;margin:0!important}
.hc-term .card-link{align-self:flex-start;margin-top:2px!important}
@media (max-width:760px){.hc-grid{grid-template-columns:1fr}}
</style>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import AppModal from '@/components/AppModal.vue'
import InfoTip from '@/components/InfoTip.vue'
import ResearchSection from '@/components/research/ResearchSection.vue'
import { footprint, tokensOf } from '@/stores/footprint.js'
import { visibleTasks, formatDate } from '@/stores/research.js'

// AI 查核：系統實際表現，對應官網要揭露的成功率、延遲、成本、錯誤類型與操作紀錄。
const rows = computed(() => footprint.records.filter((r) => r.kind === 'research'))
const done = computed(() => rows.value.filter((r) => r.status === 'completed'))
const failed = computed(() => rows.value.length - done.value.length)
const sumOf = (list, key) => list.reduce((total, row) => total + (row[key] || 0), 0)
const average = (list, key) => {
  const usable = list.filter((row) => Number.isFinite(row[key]) && row[key] > 0)
  return usable.length ? sumOf(usable, key) / usable.length : null
}
const kpis = computed(() => {
  const seconds = average(done.value, 'durationMs'), tokens = average(done.value, 'tokens'), coverage = average(done.value, 'coverage')
  return [
    { icon: 'check', label: '研究成功率', value: rows.value.length ? Math.round((done.value.length / rows.value.length) * 100) : '—', unit: rows.value.length ? '%' : '', note: `共 ${rows.value.length} 份`, tip: '已結束的研究中成功完成的比例，使用者自己取消的不計入。樣本少時不能代表整體表現。' },
    { icon: 'radar', label: '平均耗時', value: seconds == null ? '—' : (seconds / 1000).toFixed(1), unit: seconds == null ? '' : '秒', note: '從送出到完成', tip: '每份研究在後端實際執行的時間。' },
    { icon: 'layers', label: '每份 Token', value: tokens == null ? '—' : Math.round(tokens).toLocaleString('zh-TW'), unit: '', note: tokens == null ? '研究完成後計算' : 'AI 用量（成本）', tip: 'AI 處理每份研究的平均用量，已刪除的研究只計入刪除前有記錄到的。' },
    { icon: 'database', label: '平均覆蓋率', value: coverage == null ? '—' : Math.round(coverage), unit: coverage == null ? '' : '%', note: '需要的資料取得多少', tip: '研究規劃要取得的官方資料中，實際取得且有來源網址的比例。' },
    { icon: 'shield', label: '攔下句數', value: sumOf(done.value, 'rejected'), unit: '句', note: '數字對不上就刪除', tip: 'AI 寫出但對不上官方資料、被系統刪除的句數。' },
  ]
})
const REASONS = { data_wrong: '回報資料有錯', hard_to_read: '回報看不懂', too_slow: '回報太慢', off_topic: '回報沒答到問題' }
const errors = computed(() => {
  const list = [['資料來源缺漏', sumOf(done.value, 'missing')], ['數字對不上被攔下', sumOf(done.value, 'rejected')], ['研究執行失敗', failed.value]]
  Object.entries(REASONS).forEach(([key, label]) => list.push([label, footprint.records.filter((r) => r.reason === key).length]))
  return list
})
const errorMax = computed(() => Math.max(1, ...errors.value.map((e) => e[1])))
const TABLE_ROWS = 7
const tasks = computed(() => visibleTasks.value.filter((t) => ['completed', 'failed'].includes(t.status)).slice(0, TABLE_ROWS))
const opened = ref(null)
const router = useRouter()
const deletedCount = computed(() => rows.value.filter((r) => r.deleted).length)
const tokenOf = (t) => (tokensOf(t.usage) ? tokensOf(t.usage).toLocaleString('zh-TW') : '—')
const seconds = (t) => (Number.isFinite(t.backendDurationMs) ? `${(t.backendDurationMs / 1000).toFixed(1)} 秒` : '—')
</script>

<template>
  <div class="fp-kpis au-kpis" data-tour="fp-audit-kpis">
    <article v-for="kpi in kpis" :key="kpi.label" class="card surface-solid">
      <div><small>{{ kpi.label }}<InfoTip :text="kpi.tip" :label="kpi.label" /></small><strong>{{ kpi.value }}<i>{{ kpi.unit }}</i></strong><span>{{ kpi.note }}</span></div>
      <em aria-hidden="true"><AppIcon :name="kpi.icon" :size="17" /></em>
    </article>
  </div>
  <div class="au-main fp-grow">
    <section class="card surface-solid fp-card">
      <header><h2>錯誤類型</h2><small>累計次數</small></header>
      <ul class="au-errors">
        <li v-for="[label, count] in errors" :key="label" :title="`${label}：${count} 次`"><span>{{ label }}</span><i aria-hidden="true"><u v-if="count" :style="{ width: `${(count / errorMax) * 100}%` }"></u></i><b>{{ count }}</b></li>
      </ul>
    </section>
    <section class="card surface-solid fp-card">
      <header><h2>研究紀錄</h2><small>點開看 Agent 每一步</small></header>
      <div v-if="tasks.length" class="fp-table au-table">
        <div class="au-row is-head"><span>題目</span><span>日期</span><span>耗時</span><span>Token</span><span>覆蓋率</span><span>攔下</span><span></span></div>
        <div v-for="t in tasks" :key="t.id" class="au-row">
          <strong :title="t.query">{{ t.query }}</strong><span>{{ formatDate(t.createdAt) }}</span><span>{{ t.failed ? '失敗' : seconds(t) }}</span><span>{{ tokenOf(t) }}</span><span>{{ t.metrics?.coverage?.completeness_pct ?? '—' }}{{ t.metrics?.coverage ? '%' : '' }}</span><span>{{ t.metrics?.output_validation?.rejected_sentence_count ?? 0 }} 句</span>
          <button class="fp-link" type="button" @click="opened = t">查看 →</button>
        </div>
      </div>
      <div v-else class="fp-table au-table au-blank">
        <div class="au-row is-head"><span>題目</span><span>日期</span><span>耗時</span><span>Token</span><span>覆蓋率</span><span>攔下</span><span></span></div>
        <div v-for="i in 3" :key="i" class="au-row au-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
        <div class="au-blank-msg">
          <template v-if="deletedCount"><strong>已刪除 {{ deletedCount }} 份研究</strong><span>內容已清除，累計數字仍保留在左邊與上方。</span></template>
          <template v-else><strong>完成第一份研究後，這裡會列出每一步</strong><span>包含耗時、用量、資料覆蓋率，以及 Agent 做了什麼。</span></template>
          <button class="primary-button small" type="button" @click="router.push('/research')">建立研究 →</button>
        </div>
      </div>
    </section>
  </div>
  <AppModal :open="Boolean(opened)" title="Agent 執行紀錄" :modal-class="['research-section-modal', 'research-section-trace']" @close="opened = null">
    <ResearchSection v-if="opened" :key="opened.id" :task="opened" section="trace" />
  </AppModal>
</template>

<style scoped>
.au-kpis{grid-template-columns:repeat(5,minmax(0,1fr))}
.au-main{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.6fr);gap:8px}
.au-errors{flex:1;display:grid;grid-auto-rows:minmax(0,1fr);align-items:center;margin:0;padding:0;list-style:none;min-height:0}
.au-errors li{display:grid;grid-template-columns:138px minmax(0,1fr) 30px;align-items:center;gap:8px;color:var(--text);font-size:13px}
.au-errors i{display:block;height:12px;border-radius:0 4px 4px 0;background:var(--sc-track)}
.au-errors u{display:block;height:100%;border-radius:0 4px 4px 0;background:var(--sc-b)}
.au-errors b{color:var(--text-strong);text-align:right;font-variant-numeric:tabular-nums}
.au-table{display:grid;grid-template-rows:auto repeat(7,minmax(0,1fr));padding:0 14px}
.au-row{display:grid;grid-template-columns:minmax(0,1fr) 88px 56px 56px 50px 42px 44px;align-items:center;gap:10px;min-height:0;color:var(--text);font-size:13px;font-variant-numeric:tabular-nums}
.au-row + .au-row{border-top:1px solid var(--line)}
.au-row.is-head{padding:7px 0;color:var(--muted);font-size:12px;font-weight:600}
.au-row strong{overflow:hidden;color:var(--text-strong);font-weight:600;text-overflow:ellipsis;white-space:nowrap}
.au-row span{white-space:nowrap}
.au-blank{position:relative}
.au-ghost i{display:block;height:9px;border-radius:5px;background:color-mix(in srgb,var(--muted) 16%,transparent)}
.au-blank-msg{position:absolute;inset:40px 0 0;display:grid;place-content:center;justify-items:center;gap:6px;text-align:center;background:linear-gradient(transparent,var(--pw-inner) 34%)}
.au-blank-msg strong{color:var(--text-strong);font-size:15px}
.au-blank-msg span{color:var(--muted);font-size:13px}
@media (max-width:900px){.au-main{grid-template-columns:1fr}.au-table{grid-template-rows:none}}
</style>

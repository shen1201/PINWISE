<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { exportResearchPdf } from '@/utils/researchReport.js'
import { research, visibleTasks, isCompleted, statusLabel, durationText, formatDate, removeTask } from '@/stores/research.js'

// 最近研究任務：與 PINWISE 助手相同的右側整欄抽屜，平常收起，由研究頁上方的入口開啟。
const props = defineProps({ open: Boolean })
const emit = defineEmits(['close', 'select'])
const panel = ref(null)

const KEEP_OPEN = '.modal, .modal-backdrop, .toast-stack, .info-tip-bubble, [data-history-entry]'
function onOutside(event) {
  if (!props.open || panel.value?.contains(event.target) || event.target.closest?.(KEEP_OPEN)) return
  emit('close')
}
function onKeydown(event) {
  if (event.key === 'Escape' && props.open && !document.body.classList.contains('modal-open')) emit('close')
}
onMounted(() => {
  document.addEventListener('pointerdown', onOutside)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onOutside)
  document.removeEventListener('keydown', onKeydown)
})

const categoryOf = (t) => t.researchTopic || (t.researchType === 'etf' ? 'ETF' : '研究')
</script>

<template>
  <Teleport to="body">
    <aside ref="panel" class="rh-drawer" :class="{ open }" :inert="!open" :aria-hidden="String(!open)" aria-label="最近研究任務">
      <header class="rh-head">
        <div><h2>最近研究任務</h2><small>{{ visibleTasks.length ? `共 ${visibleTasks.length} 筆，只保存在此瀏覽器` : '完成的研究會列在這裡' }}</small></div>
        <button class="rh-close" type="button" aria-label="關閉最近研究任務" @click="emit('close')">✕</button>
      </header>
      <div class="rh-list">
        <article v-for="item in visibleTasks" :key="item.id" class="rh-item" :class="{ active: item.id === research.activeId }">
          <div class="rh-item-top">
            <strong :title="item.query">{{ item.query }}</strong>
            <span class="rh-status" :class="{ done: isCompleted(item) }">{{ statusLabel(item) }}</span>
          </div>
          <small>{{ categoryOf(item) }} · {{ formatDate(item.createdAt) }}<template v-if="isCompleted(item)"> · {{ durationText(item) }}</template></small>
          <div class="rh-actions">
            <button class="soft-button small" type="button" @click="emit('select', item.id)">{{ isCompleted(item) ? '查看結果' : '查看進度' }} →</button>
            <button v-if="isCompleted(item)" class="outline-button small" type="button" @click="exportResearchPdf(item)">匯出 PDF</button>
            <button class="rh-remove" type="button" :aria-label="`刪除研究：${item.query}`" @click="removeTask(item.id)">刪除</button>
          </div>
        </article>
        <div v-if="!visibleTasks.length" class="rh-empty">
          <strong>最近還沒有研究紀錄</strong>
          <p>送出第一個問題後，研究任務會出現在這裡。</p>
        </div>
      </div>
    </aside>
  </Teleport>
</template>

<style scoped>
.rh-drawer{position:fixed;top:0;right:0;bottom:0;z-index:105;display:flex;flex-direction:column;width:clamp(400px,32vw,480px);max-width:100vw;height:100dvh;border:1px solid var(--fp-border);border-right:0;border-radius:22px 0 0 22px;background:linear-gradient(180deg,rgba(236,244,255,.97) 0%,rgba(244,241,255,.97) 55%,rgba(250,244,252,.97) 100%);box-shadow:var(--fp-shadow-modal);backdrop-filter:blur(24px) saturate(1.08);-webkit-backdrop-filter:blur(24px) saturate(1.08);overflow:hidden;transform:translateX(calc(100% + 24px));transition:transform .25s ease}
.rh-drawer.open{transform:translateX(0)}
.rh-head{flex:none;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;border-bottom:1px solid var(--line)}
.rh-head h2{margin:0;color:var(--text-strong);font-size:18px}
.rh-head small{color:var(--muted);font-size:12px}
.rh-close{flex:none;width:32px;height:32px;border:0;border-radius:50%;background:transparent;color:var(--text);font-size:15px;cursor:pointer}
.rh-close:hover{background:color-mix(in srgb,var(--blue) 10%,transparent)}
.rh-list{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;display:flex;flex-direction:column;gap:10px;padding:14px}
.rh-item{flex:none;display:grid;gap:6px;padding:12px 14px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.94);box-shadow:0 4px 14px rgba(16,47,86,.06)}
.rh-item.active{border-color:var(--blue)}
.rh-item-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.rh-item-top strong{min-width:0;color:var(--text-strong);font-size:14px;line-height:1.45}
.rh-item small{color:var(--muted);font-size:12px}
.rh-status{flex:none;padding:2px 9px;border-radius:999px;background:color-mix(in srgb,var(--blue) 10%,transparent);color:var(--blue);font-size:12px;font-weight:700}
.rh-status.done{background:color-mix(in srgb,var(--green) 14%,transparent);color:var(--green)}
.rh-actions{display:flex;align-items:center;gap:8px}
.rh-remove{margin-left:auto}
.rh-remove{padding:2px 6px;border:0;border-radius:6px;background:transparent;color:var(--muted);font-size:12px;cursor:pointer}
.rh-remove:hover{background:color-mix(in srgb,var(--red) 10%,transparent);color:var(--red)}
.rh-empty{margin:auto 0;padding:24px;text-align:center}
.rh-empty strong{color:var(--text-strong)}
.rh-empty p{margin:6px 0 0;color:var(--muted);font-size:13px;line-height:1.6}
:global(body[data-theme="dark"] .rh-drawer){background:linear-gradient(180deg,#10233d 0%,#16233f 55%,#1c2240 100%)}
:global(body[data-theme="dark"] .rh-item){background:#14263f}
</style>

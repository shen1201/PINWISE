<script setup>
import { computed } from 'vue'
import AppModal from '@/components/AppModal.vue'

// ETF 完整成份股名單；股票詳情與股票比較共用同一個視窗。
const props = defineProps({
  open: Boolean,
  code: { type: String, default: '' },
  holdings: { type: Object, default: null }, // { holdings, as_of, issuer, source_url }
})
const emit = defineEmits(['close'])
const maxHolding = computed(() => Math.max(0.01, ...(props.holdings?.holdings || []).map((row) => row.weight)))
</script>

<template>
  <AppModal :open="open" :title="`${code} 成份股`" modal-class="sd-all-modal" backdrop-class="sd-all-backdrop" @close="emit('close')">
    <div v-if="holdings" class="sd-all">
      <p class="sd-all-meta">共 {{ holdings.holdings.length }} 檔，依持股權重排序<span>資料日 {{ holdings.as_of }} · <a :href="holdings.source_url" target="_blank" rel="noopener noreferrer">{{ holdings.issuer }}</a></span></p>
      <table>
        <thead><tr><th>#</th><th>代號</th><th>名稱</th><th class="sd-all-weight">持股權重</th></tr></thead>
        <tbody>
          <tr v-for="(row, index) in holdings.holdings" :key="row.code">
            <td>{{ index + 1 }}</td>
            <td><b>{{ row.code }}</b></td>
            <td :title="row.name">{{ row.name }}</td>
            <td><div class="sd-all-weight"><i aria-hidden="true"><u :style="{ width: `${Math.max(1, (row.weight / maxHolding) * 100)}%` }"></u></i><em>{{ row.weight.toFixed(2) }}%</em></div></td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppModal>
</template>

<style scoped>
:global(.modal-backdrop.sd-all-backdrop){z-index:125}
:global(.modal.sd-all-modal){z-index:130;display:flex;flex-direction:column;overflow:hidden;width:min(680px,calc(100vw - 32px))}
:global(.modal.sd-all-modal > .modal-header){flex:none;position:relative;z-index:2;background:linear-gradient(var(--surface-solid,var(--fp-surface-solid)),var(--surface-solid,var(--fp-surface-solid))),var(--surface-solid,var(--fp-surface-solid))}
:global(body[data-theme="dark"] .modal.sd-all-modal > .modal-body){color-scheme:dark}
:global(.modal.sd-all-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none;overflow:auto;padding:0 24px 20px}
.sd-all-meta{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;margin:0;padding:14px 0 10px;color:var(--muted);font-size:13px}
.sd-all-meta a{color:var(--blue)}
.sd-all table{width:100%;border-collapse:separate;border-spacing:0;table-layout:fixed;font-size:14px;color:var(--text)}
.sd-all th{position:sticky;top:-2px;z-index:1;padding:10px 6px 8px;background:linear-gradient(var(--surface-solid,var(--fp-surface-solid)),var(--surface-solid,var(--fp-surface-solid))),var(--surface-solid,var(--fp-surface-solid));box-shadow:inset 0 -1px 0 var(--line);color:var(--muted);font-size:12px;font-weight:600;text-align:left}
.sd-all th:first-child{width:44px}
.sd-all th:nth-child(2){width:112px}
.sd-all th.sd-all-weight{width:200px}
.sd-all td{padding:7px 6px;border-bottom:1px solid color-mix(in srgb,var(--line) 55%,transparent);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sd-all td:first-child{color:var(--muted);font-variant-numeric:tabular-nums}
.sd-all td b{color:var(--text-strong)}
.sd-all div.sd-all-weight{display:grid;grid-template-columns:minmax(0,1fr) 62px;align-items:center;gap:8px}
.sd-all i{display:block;height:8px;border-radius:4px;background:color-mix(in srgb,var(--blue) 10%,transparent)}
.sd-all u{display:block;height:100%;border-radius:0 4px 4px 0;background:#2A78D6}
.sd-all em{color:var(--text-strong);font-style:normal;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}
@media (max-width:640px){.sd-all th:nth-child(2){width:84px}.sd-all th.sd-all-weight{width:130px}}
</style>

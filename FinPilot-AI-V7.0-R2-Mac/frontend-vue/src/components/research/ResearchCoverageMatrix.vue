<script setup>
import { computed } from 'vue'

// 資料覆蓋矩陣：把「2330 重大訊息：目前期間沒有資料」這類逐項文字整理成「標的 × 資料集」表格。
// 來源紀錄的 source 形如「2330 市場日行情」，subjects 為 ['2330']；無 subjects 的視為全市場資料。
const props = defineProps({
  records: { type: Array, default: () => [] },
  names: { type: Object, default: () => ({}) }, // { code: name }
})

// 欄位名稱縮短，避免表格出現橫向捲軸（完整名稱在滑鼠提示）
const SHORT = { 市場日行情: '日行情', 公司基本資料: '基本資料', 歷史日行情: '歷史價', 重大訊息: '重大訊息', 法說會: '法說', 估值與財務: '財務' }

function state(r) {
  if (r.missing || r.data_status === 'missing') return { key: 'missing', mark: '—', label: r.missing_reason || '資料缺漏' }
  if (r.data_status === 'fixture') return { key: 'fixture', mark: '◇', label: '隔離資料' }
  if (!['real', 'cache'].includes(r.data_status)) return { key: 'unverified', mark: '?', label: '尚未驗證' }
  if (r.stale) return { key: 'stale', mark: '!', label: '已取得（資料較舊）' }
  return { key: 'ok', mark: '✓', label: r.data_status === 'cache' ? '已取得（快取）' : '已取得' }
}

const matrix = computed(() => {
  const columns = []
  const rows = new Map()
  const market = []
  for (const r of props.records) {
    const code = r.subjects?.length === 1 ? r.subjects[0] : ''
    const source = String(r.source || '')
    if (!code || !source.startsWith(`${code} `)) {
      market.push({ name: source || r.title || '市場資料', ...state(r) })
      continue
    }
    const dataset = source.slice(code.length + 1).trim()
    if (!columns.includes(dataset)) columns.push(dataset)
    if (!rows.has(code)) rows.set(code, {})
    rows.get(code)[dataset] = state(r)
  }
  return { columns, rows: [...rows.entries()].map(([code, cells]) => ({ code, cells })), market }
})

const counts = computed(() => {
  const all = [...matrix.value.rows.flatMap((r) => Object.values(r.cells)), ...matrix.value.market]
  return { ok: all.filter((c) => c.key === 'ok' || c.key === 'stale').length, total: all.length }
})
</script>

<template>
  <div v-if="matrix.rows.length" class="coverage-matrix">
    <div class="coverage-head">
      <strong>資料覆蓋</strong>
      <small>已取得 {{ counts.ok }}／{{ counts.total }} 項</small>
    </div>
    <div class="coverage-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">標的</th>
            <th v-for="c in matrix.columns" :key="c" scope="col" :title="c">{{ SHORT[c] || c }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in matrix.rows" :key="row.code">
            <th scope="row">{{ row.code }}<small v-if="names[row.code]">{{ names[row.code] }}</small></th>
            <td v-for="c in matrix.columns" :key="c">
              <span
                v-if="row.cells[c]"
                class="coverage-cell"
                :class="`is-${row.cells[c].key}`"
                :title="row.cells[c].label"
                :aria-label="`${row.code} ${c}：${row.cells[c].label}`"
              >{{ row.cells[c].mark }}</span>
              <span v-else class="coverage-cell is-none" aria-label="未規劃">·</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="coverage-foot">
      <span v-for="m in matrix.market" :key="m.name" class="coverage-chip">
        <span class="coverage-cell" :class="`is-${m.key}`" aria-hidden="true">{{ m.mark }}</span>{{ m.name }}
      </span>
      <span class="coverage-legend"><b class="is-ok">✓</b> 已取得 <b class="is-stale">!</b> 較舊 <b class="is-missing">—</b> 本期間無資料</span>
    </div>
  </div>
</template>

<style scoped>
.coverage-matrix{display:grid;gap:10px;margin-top:14px;padding:14px;border:1px solid var(--line);border-radius:var(--radius-md)}
.coverage-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.coverage-head strong{color:var(--text-strong);font-size:15px}
.coverage-head small{color:var(--muted);font-size:13px}
.coverage-scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 6px;text-align:center;border-bottom:1px solid var(--line);white-space:nowrap}
thead th{color:var(--muted);font-weight:600;font-size:12px}
tbody th{text-align:left;color:var(--text-strong);font-weight:700}
tbody th small{display:block;margin-left:0;color:var(--muted);font-weight:400;font-size:11px}
tbody tr:last-child th,tbody tr:last-child td{border-bottom:0}
.coverage-cell{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:7px;font-weight:700;font-size:13px}
.is-ok{color:var(--green);background:color-mix(in srgb,var(--green) 14%,transparent)}
.is-stale{color:var(--orange);background:color-mix(in srgb,var(--orange) 16%,transparent)}
.is-missing{color:var(--red);background:color-mix(in srgb,var(--red) 10%,transparent)}
.is-fixture,.is-unverified{color:var(--purple);background:color-mix(in srgb,var(--purple) 12%,transparent)}
.is-none{color:var(--muted)}
.coverage-foot{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 14px;font-size:13px;color:var(--text)}
.coverage-chip{display:inline-flex;align-items:center;gap:6px}
.coverage-legend{display:inline-flex;align-items:center;gap:6px;color:var(--muted);font-size:12px}
.coverage-legend b{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:5px;font-size:11px}
</style>

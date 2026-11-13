import { formatDate, symbolName } from '@/stores/research.js'

// 研究報告匯出：組成一份獨立的列印頁，交給瀏覽器「另存為 PDF」，不需要額外套件。
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const list = (items, tag = 'ul') => `<${tag}>${items.map((x) => `<li>${esc(x)}</li>`).join('')}</${tag}>`
const section = (title, body) => (body ? `<section><h2>${esc(title)}</h2>${body}</section>` : '')
const fmt = (v, unit, signed) => (Number.isFinite(v) ? `${signed && v > 0 ? '+' : ''}${Math.round(v * 100) / 100}${unit}` : '—')

const COLUMNS = [
  ['period_return_pct', '期間報酬', '%', true],
  ['annualized_volatility_pct', '年化波動', '%', false],
  ['revenue_yoy_pct', '月營收年增', '%', true],
  ['pe_ratio', '本益比', ' 倍', false],
  ['dividend_yield_pct', '殖利率', '%', false],
]

function comparisonTable(task) {
  const codes = task.candidates || []
  if (!codes.length) return ''
  const rows = codes.map((code) => {
    const m = task.metrics?.[code] || {}
    return `<tr><td><b>${esc(code)}</b> ${esc(symbolName(task, code))}</td>${COLUMNS.map(([key, , unit, signed]) => `<td class="num">${fmt(m[key], unit, signed)}</td>`).join('')}</tr>`
  })
  return `<table><thead><tr><th>標的</th>${COLUMNS.map(([, label]) => `<th class="num">${label}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`
}

function sourcesTable(task) {
  const records = task.sourceRecords || []
  if (!records.length) return ''
  const rows = records.map((r) => `<tr><td>${esc(r.subjects?.join('、') || '全市場')}</td><td>${esc(String(r.source || r.title || '').replace(/^\d{4,6}[A-Z]?\s*/, ''))}</td><td>${esc(r.latest_data_at || r.period_end || '—')}</td><td>${r.missing ? '本期間無資料' : '已取得'}</td></tr>`)
  return `<table><thead><tr><th>標的</th><th>資料</th><th>資料日</th><th>狀態</th></tr></thead><tbody>${rows.join('')}</tbody></table>`
}

export function buildReportHtml(task) {
  const first = task.metrics?.[task.candidates?.[0]] || {}
  const period = first.period_start ? `${first.period_start} ～ ${first.period_end}` : task.metrics?.query_period?.applied_horizon || task.horizon || '預設近 6 個月'
  const coverage = task.metrics?.coverage
  const meta = [
    ['研究時間', formatDate(task.createdAt)],
    ['資料期間', period],
    ...(task.focusLabel ? [['研究重點', task.focusLabel]] : []),
    ...(coverage ? [['資料覆蓋', `${coverage.completeness_pct}%（${coverage.available_sources}/${coverage.total_sources} 項）`]] : []),
  ]
  const watch = (task.watchItems || []).map((w) => `${w.symbol ? `${w.symbol}：` : ''}${w.item}${w.why ? `（${w.why}）` : ''}`)
  const limitations = [...new Set(task.limitations || [])]
  return `<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>${esc(`PINWISE 研究報告_${task.query}`.slice(0, 80))}</title><style>
@page{size:A4;margin:16mm 14mm}
*{box-sizing:border-box}
body{margin:0;color:#1a2b45;font:13px/1.7 -apple-system,"PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif}
header{padding-bottom:10px;border-bottom:2px solid #2a78d6}
header small{color:#2a78d6;font-weight:700;letter-spacing:.08em}
h1{margin:2px 0 8px;font-size:21px;line-height:1.35}
.meta{display:flex;flex-wrap:wrap;gap:4px 22px;color:#566b87;font-size:12px}
.meta b{color:#1a2b45}
section{margin-top:16px}
h2{margin:0 0 6px;font-size:15px;color:#123a75}
p{margin:0 0 6px}
ul,ol{margin:0;padding-left:20px}
li{margin-bottom:3px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:5px 6px;border-bottom:1px solid #d9e2ef;text-align:left;vertical-align:top}
th{background:#eef4fc;color:#566b87}
.num{text-align:right;font-variant-numeric:tabular-nums}
tr,li{break-inside:avoid}
h2{break-after:avoid}
footer{margin-top:18px;padding-top:8px;border-top:1px solid #d9e2ef;color:#566b87;font-size:11px}
</style></head><body>
<header><small>PINWISE 研究報告</small><h1>${esc(task.query)}</h1><div class="meta">${meta.map(([k, v]) => `<span>${esc(k)}：<b>${esc(v)}</b></span>`).join('')}</div></header>
${section('研究摘要', String(task.summary || '').split(/\n+/).filter(Boolean).map((x) => `<p>${esc(x)}</p>`).join(''))}
${section('重點比較', comparisonTable(task))}
${section('主要風險', task.risks?.length ? list(task.risks, 'ol') : '')}
${section('可能推翻結論的條件', task.invalidationConditions?.length ? list(task.invalidationConditions) : '')}
${section('後續觀察條件', watch.length ? list(watch) : '')}
${section('資料限制', limitations.length ? list(limitations) : '')}
${section('資料來源', sourcesTable(task))}
<footer>本報告由 AI 依官方公開資料與程式計算結果整理，僅供研究與學習參考，不構成投資建議。過去表現不代表未來結果。</footer>
</body></html>`
}

export function exportResearchPdf(task) {
  const frame = document.createElement('iframe')
  frame.setAttribute('aria-hidden', 'true')
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'
  frame.srcdoc = buildReportHtml(task)
  frame.onload = () => {
    frame.contentWindow.focus()
    frame.contentWindow.print()
    // 列印視窗關閉前不能移除 iframe；Safari 不一定觸發 afterprint，用時間保底。
    setTimeout(() => frame.remove(), 60000)
  }
  document.body.appendChild(frame)
}

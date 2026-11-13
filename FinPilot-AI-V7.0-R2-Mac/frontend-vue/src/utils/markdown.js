// 搬自 js/ui.js 的 assistantMarkdown：先跳脫 HTML 再套用有限的 Markdown，輸出可安全用於 v-html。
export function esc(value = '') {
  return String(value).replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[c])
}

function safeLink(value) {
  try {
    const url = new URL(String(value || ''), location.href)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null
  } catch {
    return null
  }
}

function inline(value) {
  const tokens = []
  const hold = (html) => {
    const key = `\u0000${tokens.length}\u0000`
    tokens.push(html)
    return key
  }
  let source = String(value || '')
  source = source.replace(/`([^`\n]+)`/g, (_, code) => hold(`<code>${esc(code)}</code>`))
  source = source.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (_, label, url) => {
    const safe = safeLink(url)
    return safe ? hold(`<a href="${esc(safe)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`) : `${label} (${url})`
  })
  let html = esc(source)
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>')
  tokens.forEach((token, index) => {
    html = html.split(`\u0000${index}\u0000`).join(token)
  })
  return html
}

// Markdown 表格：| a | b | 加上 |---|---:| 分隔列；冒號在右代表靠右對齊。
const TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/
const splitRow = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
function renderTable(rows) {
  const align = splitRow(rows[1]).map((cell) => (cell.endsWith(':') ? 'right' : 'left'))
  const cell = (tag, text, i) => `<${tag} style="text-align:${align[i] || 'left'}">${inline(text)}</${tag}>`
  const head = splitRow(rows[0]).map((text, i) => cell('th', text, i)).join('')
  const body = rows.slice(2).map((row) => `<tr>${splitRow(row).map((text, i) => cell('td', text, i)).join('')}</tr>`).join('')
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`
}

export function markdown(value) {
  const lines = String(value || '').replace(/\r\n?/g, '\n').split('\n')
  const out = []
  // listItems：{ text, children: [] }；縮排 2 格以上的項目放進上一個項目的子清單（支援兩層）。
  let paragraph = [], listType = '', listItems = [], quote = [], code = [], inCode = false, table = []
  const flushParagraph = () => {
    if (paragraph.length) out.push(`<p>${paragraph.map(inline).join('<br>')}</p>`)
    paragraph = []
  }
  const flushList = () => {
    const sub = (item) => (item.children.length ? `<${item.childType}>${item.children.map((c) => `<li>${inline(c)}</li>`).join('')}</${item.childType}>` : '')
    if (listItems.length) out.push(`<${listType}>${listItems.map((item) => `<li>${inline(item.text)}${sub(item)}</li>`).join('')}</${listType}>`)
    listItems = []
    listType = ''
  }
  const flushTable = () => {
    if (table.length >= 2 && TABLE_SEPARATOR.test(table[1])) out.push(renderTable(table))
    else if (table.length) paragraph.push(...table)
    table = []
  }
  const flushQuote = () => {
    if (quote.length) out.push(`<blockquote>${quote.map(inline).join('<br>')}</blockquote>`)
    quote = []
  }
  const flushAll = () => {
    flushTable()
    flushParagraph()
    flushList()
    flushQuote()
  }
  for (const line of lines) {
    if (/^```/.test(line)) {
      flushAll()
      if (inCode) {
        out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`)
        code = []
      }
      inCode = !inCode
      continue
    }
    if (inCode) {
      code.push(line)
      continue
    }
    if (/^\s*\|/.test(line)) {
      if (!table.length) {
        flushParagraph()
        flushList()
        flushQuote()
      }
      table.push(line)
      continue
    }
    if (table.length) flushTable()
    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushAll()
      const level = Math.min(4, heading[1].length + 2)
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`)
      continue
    }
    const unordered = line.match(/^(\s*)[-*+]\s+(.+)$/)
    const ordered = line.match(/^(\s*)\d+[.)]\s+(.+)$/)
    if (unordered || ordered) {
      flushParagraph()
      flushQuote()
      const [, indent, text] = unordered || ordered
      const type = ordered ? 'ol' : 'ul'
      const parent = listItems.at(-1)
      if (indent.replace(/\t/g, '  ').length >= 2 && parent) {
        parent.childType = parent.childType || type
        parent.children.push(text)
        continue
      }
      if (listType && listType !== type) flushList()
      listType = type
      listItems.push({ text, children: [], childType: '' })
      continue
    }
    const quoted = line.match(/^>\s?(.*)$/)
    if (quoted) {
      flushParagraph()
      flushList()
      quote.push(quoted[1])
      continue
    }
    // 空行不結束清單：AI 常在項目之間空一行，若結束清單，下一個縮排的子項目會變成同一層。
    // 下一行不是清單項目時，會在下面的 flushList() 結束。
    if (!line.trim()) {
      flushTable()
      flushParagraph()
      flushQuote()
      continue
    }
    flushList()
    flushQuote()
    paragraph.push(line)
  }
  if (inCode) out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`)
  flushAll()
  return out.join('')
}

import { computed, onMounted, ref } from 'vue'
import { api } from '@/api/client.js'

// 常用標的：取最近交易日成交金額最高的個股；抓不到時退回這份常見標的。
const FALLBACK = [['2330', '台積電'], ['2454', '聯發科'], ['6488', '環球晶'], ['2308', '台達電'], ['0050', '元大台灣50'], ['00878', '國泰永續高股息']]
const LIMIT = 6

export function usePopularStocks() {
  const top = ref([])
  const date = ref('')
  onMounted(async () => {
    try {
      const { items = [] } = await api.selectStocks({ product_type: 'stock', limit: LIMIT })
      top.value = items.map((item) => [item.symbol, item.name])
      date.value = items[0]?.quote?.trade_date || ''
    } catch {
      top.value = []
    }
  })
  return { popular: computed(() => (top.value.length ? top.value : FALLBACK)), date }
}

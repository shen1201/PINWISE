<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import AppDrawer from './AppDrawer.vue'
import { settings, unreadCount } from '@/stores/ui.js'
import { overlays, openStockDetail } from '@/stores/overlays.js'
import { research } from '@/stores/research.js'

// 通知中心（對應舊版 openNotificationDrawer）。
const router = useRouter()
const filter = ref('all')
// 分頁與設定頁的通知開關一一對應（研究／追蹤／系統）。
const TABS = [['all', '全部'], ['unread', '未讀'], ['research', 'AI 標的研究'], ['tracking', '追蹤股票'], ['system', '系統狀態']]

const EMPTY_TEXT = {
  all: '研究完成、追蹤股票大漲大跌或有新公告時，會顯示在這裡。',
  research: 'AI 標的研究完成或失敗時會顯示在這裡。',
  tracking: '追蹤股票單日漲跌超過 7%、從高點回落超過提醒線，或有新公告時通知。',
  system: '官方資料連不上、AI 每日額度用完時通知。',
}
const list = computed(() =>
  settings.notifications.filter((n) => filter.value === 'all' || (filter.value === 'unread' && !n.read) || n.type === filter.value),
)

// 點通知：研究 → 打開那份研究；有頁面連結 → 前往；有股票代號 → 打開股票詳情。
function read(n) {
  n.read = true
  if (n.type === 'research' && research.tasks.some((t) => t.id === n.taskId && !t.deletedAt)) {
    research.activeId = n.taskId
    overlays.notifications = false
    router.push('/research')
  } else if (n.link) {
    overlays.notifications = false
    router.push(n.link)
  } else if (n.code) {
    overlays.notifications = false
    openStockDetail(n.code, '股票詳情')
  }
}
const remove = (n) => (settings.notifications = settings.notifications.filter((x) => x.id !== n.id))
const markAll = () => settings.notifications.forEach((n) => (n.read = true))
</script>

<template>
  <AppDrawer :open="overlays.notifications" title="通知中心" eyebrow="PINWISE 通知" @close="overlays.notifications = false">
    <div class="notification-tabs">
      <button v-for="[key, label] in TABS" :key="key" type="button" :class="{ active: filter === key }" @click="filter = key">{{ label }}</button>
    </div>
    <p class="nd-note">網頁開著時每 10 分鐘檢查一次；行情為收盤日資料，不是盤中即時。</p>
    <div class="notification-actions">
      <button class="soft-button" type="button" :disabled="!unreadCount" @click="markAll">全部已讀</button>
    </div>
    <div class="notification-list">
      <article v-for="n in list" :key="n.id" class="notification-item" :class="{ read: n.read }">
        <button class="notification-main" type="button" @click="read(n)">
          <span class="notification-status"></span>
          <div><strong>{{ n.title }}</strong><p>{{ n.body }}</p><small>{{ n.time }}</small></div>
        </button>
        <button class="notification-delete" type="button" :aria-label="`刪除通知：${n.title}`" @click="remove(n)">⌫</button>
      </article>
      <div v-if="!list.length" class="empty-state">
        <strong>{{ filter === 'unread' ? '目前沒有未讀通知' : '目前沒有通知' }}</strong>
        <span>{{ EMPTY_TEXT[filter] || EMPTY_TEXT.all }}</span>
      </div>
    </div>
  </AppDrawer>
</template>

<style scoped>
.nd-note{margin:0 0 8px;color:var(--muted);font-size:12px;line-height:1.5}
</style>

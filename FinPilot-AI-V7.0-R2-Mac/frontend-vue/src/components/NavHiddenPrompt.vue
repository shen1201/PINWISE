<script setup>
import { ref, computed, watch } from 'vue'
import AppModal from './AppModal.vue'
import { navMeta } from '@/data/nav.js'
import { navReminder, showNav, dismissNavReminder } from '@/stores/navReminder.js'

// 加入比較／追蹤時，對應頁面已從側邊欄隱藏的提醒視窗。
const snooze = ref(false)
const key = computed(() => navReminder.key)
const name = computed(() => navMeta[key.value]?.[1] || '')
const WHAT = { compare: '加入比較的股票', candidates: '加入追蹤的股票' }
watch(key, () => (snooze.value = false))
</script>

<template>
  <AppModal :open="Boolean(key)" title="側邊欄入口已關閉" modal-class="nav-hidden-modal" @close="dismissNavReminder(key, snooze)">
    <div class="nhp-body">
      <p>「<strong>{{ name }}</strong>」目前已從側邊欄隱藏，{{ WHAT[key] || '剛加入的項目' }}要到這個頁面才看得到。</p>
      <p class="nhp-sub">要現在把它顯示在側邊欄嗎？之後也可以到「設定 → 外觀與版面 → 側邊欄管理」自行開啟。</p>
      <label class="nhp-check"><input v-model="snooze" type="checkbox" /> 今天不再提醒</label>
      <div class="nhp-actions">
        <button class="outline-button" type="button" @click="dismissNavReminder(key, snooze)">稍後自行設定</button>
        <button class="primary-button" type="button" @click="showNav(key)">現在顯示</button>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
:global(.modal.nav-hidden-modal){width:min(460px,calc(100vw - 32px))}
.nhp-body{display:grid;gap:10px}
.nhp-body p{margin:0;color:var(--text);font-size:15px;line-height:1.65}
.nhp-sub{color:var(--muted)!important;font-size:13px!important}
.nhp-check{display:inline-flex;align-items:center;gap:8px;margin-top:4px;color:var(--text);font-size:14px;cursor:pointer}
.nhp-check input{width:16px;height:16px;accent-color:var(--blue)}
.nhp-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:6px}
</style>

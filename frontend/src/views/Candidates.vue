<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref<any[]>([])
const papers = ref<any[]>([])
const msg = ref('')

onMounted(async () => {
  rows.value = await api('/candidates')
  papers.value = await api('/papers')
})

async function changePaper(c: any, ev: Event) {
  const pid = Number((ev.target as HTMLSelectElement).value)
  msg.value = ''
  try {
    await api(`/candidates/${c.id}`, { method: 'PATCH', body: JSON.stringify({ paper_id: pid }) })
    c.paper_id = pid
    msg.value = `${c.name} 套别已改为 卷${pid}：仅影响之后的新排座，历史方案保持不变`
  } catch (e: any) {
    msg.value = `保存失败：${e.message}`
  }
}
</script>

<template>
  <h1>考生名册</h1>
  <p class="sub">夹板名册样式 · 改套别仅影响新排座，历史方案钉住不变</p>
  <div class="hs-clipboard" style="max-width:460px">
    <h2>考生名册 · Clipboard</h2>
    <div v-for="r in rows" :key="r.id ?? JSON.stringify(r)" class="hs-roster-row">
      <div>
        <div>{{ r.name }}</div>
        <div class="hs-ticket">{{ r.ticket_no }}</div>
      </div>
      <div>
        <select :value="r.paper_id" @change="changePaper(r, $event)">
          <option v-for="p in papers" :key="p.id" :value="p.id">卷{{ p.id }} · {{ p.code }}</option>
        </select>
        · 室{{ r.hall_id }}
      </div>
    </div>
    <p v-if="msg" class="muted" style="padding:0.4rem 0.75rem;margin:0">{{ msg }}</p>
  </div>
</template>

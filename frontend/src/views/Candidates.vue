<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref<any[]>([])
const papers = ref<any[]>([])
const savingId = ref<number | null>(null)
const savedId = ref<number | null>(null)

onMounted(async () => {
  [rows.value, papers.value] = await Promise.all([api('/candidates'), api('/papers')])
})

async function changePaper(c: any) {
  savingId.value = c.id
  savedId.value = null
  try {
    const updated = await api(`/candidates/${c.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ paper_id: Number(c.paper_id) }),
    })
    c.paper_id = updated.paper_id
    savedId.value = c.id
  } finally {
    savingId.value = null
  }
}
</script>

<template>
  <h1>考生名册 · 现行套别</h1>
  <p class="sub">改套别只影响新排座与历史的漂移判定，<strong>不改历史座位</strong>。</p>
  <div class="card">
    <table>
      <thead><tr><th>姓名</th><th>准考证</th><th>现行套别</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.name }}</td>
          <td>{{ r.ticket_no }}</td>
          <td>
            <select v-model="r.paper_id" @change="changePaper(r)">
              <option v-for="p in papers" :key="p.id" :value="p.id">{{ p.code }} · {{ p.title }}</option>
            </select>
          </td>
          <td>
            <span v-if="savingId === r.id" class="muted" style="font-size:0.75rem">保存中…</span>
            <span v-else-if="savedId === r.id" class="badge badge-ok">已改（历史只亮漂移）</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

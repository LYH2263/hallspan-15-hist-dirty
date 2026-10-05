<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref<any[]>([])
const edit = ref<Record<number, { min: number; blocked: string }>>({})
const msg = ref('')

async function load() {
  rows.value = await api('/halls')
  const m: Record<number, { min: number; blocked: string }> = {}
  for (const r of rows.value) {
    m[r.id] = {
      min: r.min_manhattan,
      blocked: (r.blocked_seats || []).map((p: number[]) => p.join(',')).join('; '),
    }
  }
  edit.value = m
}
onMounted(load)

function parseBlocked(text: string): number[][] {
  const out: number[][] = []
  for (const seg of text.split(/[;；]/)) {
    const t = seg.trim()
    if (!t) continue
    const m = t.match(/^(\d+)\s*[,，]\s*(\d+)$/)
    if (!m) throw new Error(`禁坐格式错误：「${t}」，应为 行,列；如 0,1; 2,3`)
    out.push([Number(m[1]), Number(m[2])])
  }
  return out
}

async function save(h: any) {
  msg.value = ''
  try {
    const body = {
      min_manhattan: Number(edit.value[h.id].min),
      blocked_seats: parseBlocked(edit.value[h.id].blocked),
    }
    await api(`/halls/${h.id}`, { method: 'PATCH', body: JSON.stringify(body) })
    await load()
    msg.value = `考室 ${h.code} 约束已更新：仅影响之后的新排座，历史方案保持不变`
  } catch (e: any) {
    msg.value = `保存失败：${e.message}`
  }
}
</script>

<template>
  <h1>考室</h1>
  <p class="sub">考室网格与现网约束（最小间距 / 禁坐）· 改约束不影响历史方案</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>行</th><th>列</th><th>最小间距</th><th>禁坐格（行,列; …）</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.rows }}</td><td>{{ r.cols }}</td>
          <td>
            <input v-model="edit[r.id].min" type="number" min="1" max="10" class="hs-input" style="width:4rem" />
          </td>
          <td>
            <input v-model="edit[r.id].blocked" class="hs-input" style="width:14rem" placeholder="如 0,1; 2,3" />
          </td>
          <td><button class="btn" @click="save(r)">保存约束</button></td>
        </tr>
      </tbody>
    </table>
    <p v-if="msg" class="muted" style="margin:0.5rem 0 0">{{ msg }}</p>
  </div>
</template>

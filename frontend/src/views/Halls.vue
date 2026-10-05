<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const hall = ref<any>(null)
const minDist = ref<number>(2)
const saving = ref(false)
const saved = ref(false)

async function load() {
  const rows = await api<any[]>('/halls')
  hall.value = rows[0]
  if (hall.value) minDist.value = hall.value.min_manhattan
}
onMounted(load)

const rowsN = computed(() => hall.value?.rows ?? 0)
const colsN = computed(() => hall.value?.cols ?? 0)
const blockedSet = computed(() => new Set<string>((hall.value?.blocked_seats || []).map((p: number[]) => `${p[0]},${p[1]}`)))
const cells = computed(() => {
  const out: { r: number; c: number }[] = []
  for (let r = 0; r < rowsN.value; r++)
    for (let c = 0; c < colsN.value; c++) out.push({ r, c })
  return out
})
function key(r: number, c: number) { return `${r},${c}` }
function toggle(r: number, c: number) {
  const cur: number[][] = (hall.value.blocked_seats || []).map((p: number[]) => [...p])
  const idx = cur.findIndex(p => p[0] === r && p[1] === c)
  if (idx >= 0) cur.splice(idx, 1); else cur.push([r, c])
  hall.value.blocked_seats = cur
  saved.value = false
}
async function save() {
  saving.value = true
  try {
    hall.value = await api(`/halls/${hall.value.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ min_manhattan: minDist.value, blocked_seats: hall.value.blocked_seats }),
    })
    saved.value = true
  } finally { saving.value = false }
}
</script>

<template>
  <h1>考室 · 现网约束</h1>
  <p class="sub">改动立即生效于<strong>之后新排</strong>的方案；历史方案座位不变，只会被亮漂移标记。</p>
  <div class="card" v-if="hall">
    <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap">
      <label style="font-size:0.85rem">
        最小曼哈顿距离
        <input type="number" min="1" v-model.number="minDist" @input="saved = false"
          style="width:5rem;margin-left:0.4rem;padding:0.25rem">
      </label>
      <button class="btn" @click="save" :disabled="saving">{{ saving ? '保存中…' : '保存现网约束' }}</button>
      <span v-if="saved" class="badge badge-ok">已保存（不影响历史方案）</span>
    </div>
    <p class="muted" style="font-size:0.78rem;margin:0.6rem 0 0.4rem">
      点击格位切换<strong>禁坐</strong>（橙色叉格）。禁坐只作用于新排座；历史已占用的座位不会被搬走，只会亮漂移。
    </p>
    <div class="hs-block-editor" :style="{ gridTemplateColumns: `repeat(${colsN}, 34px)` }">
      <button
        v-for="(cell, i) in cells" :key="i"
        class="hs-block-cell" :class="{ on: blockedSet.has(key(cell.r, cell.c)) }"
        :title="`${cell.r},${cell.c}`" @click="toggle(cell.r, cell.c)"
        type="button"
      ></button>
    </div>
    <div class="muted" style="font-size:0.76rem;margin-top:0.5rem">
      网格 {{ hall.rows }}×{{ hall.cols }} · 已禁坐 {{ (hall.blocked_seats || []).length }} 格
    </div>
  </div>
</template>

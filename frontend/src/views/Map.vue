<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const data = ref<any>(null)          // 当前查看的方案（含钉住的座位/违规 + 漂移标记）
const plans = ref<any[]>([])         // 历史方案清单（新的在前）
const selectedId = ref<number | null>(null)
const candidates = ref<any[]>([])
const busy = ref(false)

async function loadPlans() {
  plans.value = await api('/seating/plans?hall_id=1')
}
async function openPlan(id: number) {
  data.value = await api(`/seating/plans/${id}`)
  selectedId.value = id
}
// 显式“重新排座”：按现网约束生成新方案；打开页面本身绝不触发重排
async function run() {
  busy.value = true
  try {
    const res = await api('/seating/run?hall_id=1', { method: 'POST' })
    await loadPlans()
    await openPlan(res.id)
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  candidates.value = await api('/candidates')
  await loadPlans()
  const latest = await api('/seating/latest?hall_id=1')
  await openPlan(latest.id)
})

const isLatest = computed(() => plans.value.length > 0 && selectedId.value === plans.value[0].id)
const gridStyle = computed(() => data.value ? ({ gridTemplateColumns: `repeat(${data.value.cols}, 72px)` }) : {})

// 违规高亮取自本方案存盘的违规列表（钉在生成当时），不再另取 latest
const violKeys = computed(() => {
  const keys = new Set<string>()
  for (const v of data.value?.violations || []) {
    if (v.a_id != null) keys.add(String(v.a_id))
    if (v.b_id != null) keys.add(String(v.b_id))
  }
  return keys
})
const blockedKeys = computed(() =>
  new Set((data.value?.blocked_seats || []).map((p: number[]) => p[0] + ',' + p[1])))

const cells = computed(() => {
  if (!data.value) return []
  const map = new Map<string, any>()
  for (const a of data.value.assignments || []) map.set(a.row + ',' + a.col, a)
  const out: any[] = []
  for (let r = 0; r < data.value.rows; r++) {
    for (let c = 0; c < data.value.cols; c++) {
      if (blockedKeys.value.has(r + ',' + c)) out.push({ blocked: true, row: r, col: c })
      else out.push(map.get(r + ',' + c) || { empty: true, row: r, col: c })
    }
  }
  return out
})

function isViol(cell: any) {
  if (cell.empty || cell.blocked) return false
  const id = cell.candidate_id ?? cell.id
  return id != null && violKeys.value.has(String(id))
}
function paperClass(pid: number) {
  return pid % 2 === 0 ? 'b' : 'a'
}

// 漂移标记文案：只标不修
const driftText = computed(() => {
  const d = data.value?.drift
  if (!d?.has_drift) return ''
  const parts: string[] = []
  if (d.min_manhattan) parts.push(`最小间距 ${d.min_manhattan.then} → ${d.min_manhattan.now}`)
  if (d.blocked_added?.length) parts.push(`新增禁坐 ${d.blocked_added.length} 格`)
  if (d.blocked_removed?.length) parts.push(`取消禁坐 ${d.blocked_removed.length} 格`)
  if (d.paper_changes?.length) parts.push(`套别变更 ${d.paper_changes.length} 人`)
  return parts.join(' · ')
})

function planLabel(p: any) {
  const t = p.created_at ? String(p.created_at).replace('T', ' ').slice(0, 19) : ''
  return `方案 #${p.id} · ${t} · 最小距 ${p.min_manhattan} · 坐 ${p.stats?.seated ?? '-'}`
}
</script>

<template>
  <h1>考场课桌网格</h1>
  <p class="sub">课桌网格为主视图 · 历史方案只读 · 约束漂移只标不修</p>

  <div class="hs-plan-bar">
    <select :value="selectedId ?? ''" @change="openPlan(Number(($event.target as HTMLSelectElement).value))">
      <option v-for="p in plans" :key="p.id" :value="p.id">{{ planLabel(p) }}</option>
    </select>
    <span v-if="isLatest" class="badge badge-ok">当前方案</span>
    <span v-else class="badge badge-warn">历史方案 · 只读</span>
    <button class="btn" :disabled="busy" @click="run">按现网约束重新排座</button>
  </div>

  <div v-if="data?.drift?.has_drift" class="hs-drift">
    ⚠ 约束已漂移（仅标记，不改写历史）：{{ driftText }}
  </div>

  <div class="hs-classroom" style="margin-top:0.85rem">
    <aside class="hs-clipboard">
      <h2>考生名册</h2>
      <div v-for="c in candidates" :key="c.id" class="hs-roster-row">
        <div>
          <div>{{ c.name }}</div>
          <div class="hs-ticket">{{ c.ticket_no }}</div>
        </div>
        <div>卷{{ c.paper_id }}</div>
      </div>
    </aside>
    <div class="hs-desk-stage" v-if="data">
      <div class="hs-grid-board" :style="gridStyle">
        <div
          v-for="(cell,i) in cells" :key="i"
          class="hs-desk"
          :class="{ empty: cell.empty, 'hs-viol': isViol(cell), 'hs-blocked': cell.blocked }"
        >
          <template v-if="cell.blocked">禁坐</template>
          <template v-else-if="!cell.empty">
            <span class="hs-paper-tag" :class="paperClass(cell.paper_id)">卷{{ cell.paper_id }}</span>
            <div>{{ cell.name }}</div>
          </template>
          <template v-else>·</template>
        </div>
      </div>
    </div>
  </div>
</template>

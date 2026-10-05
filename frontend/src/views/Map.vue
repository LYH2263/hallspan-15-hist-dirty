<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

interface PlanSummary { id: number; created_at: string; constraints: any; stats: any }

const data = ref<any>(null)
const plans = ref<PlanSummary[]>([])
const selectedId = ref<number | null>(null)
const candidates = ref<any[]>([])
const papers = ref<any[]>([])
const halls = ref<any[]>([])
const loading = ref(false)
const msg = ref('')

const violKeys = computed(() => {
  const keys = new Set<string>()
  for (const x of data.value?.violations || []) {
    if (x.a_id != null) keys.add(String(x.a_id))
    if (x.b_id != null) keys.add(String(x.b_id))
  }
  return keys
})
// 漂移标记与冻结违规分开，琥珀色，绝不冒充红色违规
const driftKeys = computed(() => new Set<string>(data.value?.drift?.involved_candidate_ids?.map(String) || []))
const driftItems = computed(() => data.value?.drift?.items || [])

async function loadPlans() {
  const res = await api<{ plans: PlanSummary[] }>('/seating/plans?hall_id=1')
  plans.value = res.plans
}

async function openPlan(id: number) {
  selectedId.value = id
  data.value = await api(`/seating/plan/${id}`)
}

async function runNew() {
  // 按**现网**约束出新图（INSERT 新方案，历史不动）
  loading.value = true
  msg.value = ''
  try {
    data.value = await api('/seating/run?hall_id=1', { method: 'POST', body: JSON.stringify({ hall_id: 1 }) })
    selectedId.value = data.value.id
    await loadPlans()
    msg.value = `已按现网约束生成新方案 #${data.value.id}`
  } finally { loading.value = false }
}

onMounted(async () => {
  [candidates.value, papers.value, halls.value] = await Promise.all([
    api('/candidates'), api('/papers'), api('/halls'),
  ])
  await loadPlans()
  if (plans.value.length) await openPlan(plans.value[0].id)
})

const hall = computed(() => halls.value[0] || {})
const gridStyle = computed(() => data.value ? ({ gridTemplateColumns: `repeat(${data.value.cols}, 72px)` }) : {})
const blockedSet = computed(() => new Set<string>((hall.value.blocked_seats || []).map((p: number[]) => `${p[0]},${p[1]}`)))

const cells = computed(() => {
  if (!data.value) return []
  const map = new Map<string, any>()
  for (const a of data.value.assignments || []) map.set(a.row + ',' + a.col, a)
  const out: any[] = []
  for (let r = 0; r < data.value.rows; r++) {
    for (let c = 0; c < data.value.cols; c++) {
      out.push(map.get(r + ',' + c) || { empty: true, row: r, col: c })
    }
  }
  return out
})
function isViol(cell: any) {
  if (cell.empty) return false
  return violKeys.value.has(String(cell.candidate_id))
}
function isDrift(cell: any) {
  if (cell.empty) return false
  return !isViol(cell) && driftKeys.value.has(String(cell.candidate_id))
}
function isBlockedNow(cell: any) { return blockedSet.value.has(`${cell.row},${cell.col}`) }
function paperClass(pid: number) { return pid % 2 === 0 ? 'b' : 'a' }
function paperTitle(pid: number) { return papers.value.find(p => p.id === pid)?.code || `卷${pid}` }
function fmtTime(s: string) { return new Date(s).toLocaleString('zh-CN', { hour12: false }) }
</script>

<template>
  <h1>考场课桌网格</h1>
  <p class="sub">历史方案只读：座位与违规钉在生成当时；现网约束不一致只亮琥珀色漂移标记，不重排历史。</p>

  <div class="card" style="display:flex;flex-wrap:wrap;gap:0.75rem;align-items:center">
    <label class="muted" style="font-size:0.82rem">
      历史方案
      <select :value="selectedId ?? ''" @change="openPlan(Number(($event.target as HTMLSelectElement).value))" style="margin-left:0.4rem">
        <option v-for="p in plans" :key="p.id" :value="p.id">
          #{{ p.id }} · {{ fmtTime(p.created_at) }} · 最小距 {{ p.constraints?.min_manhattan ?? '?' }}
        </option>
        <option value="" disabled v-if="!plans.length">（暂无，点右侧生成）</option>
      </select>
    </label>
    <button class="btn" @click="runNew" :disabled="loading">
      {{ loading ? '排座中…' : '按现网约束重新排座（新方案）' }}
    </button>
    <span class="muted" style="font-size:0.78rem">
      现网最小距 {{ hall.min_manhattan }} · 禁坐 {{ (hall.blocked_seats || []).length }} 格
    </span>
    <span v-if="msg" class="badge badge-ok">{{ msg }}</span>
  </div>

  <div v-if="data" class="card" style="font-size:0.8rem">
    <span class="badge" :class="data.constraint_diff?.min_manhattan?.changed ? 'badge-warn' : 'badge-ok'">
      最小距：历史 {{ data.constraints?.min_manhattan ?? '—' }} / 现网 {{ hall.min_manhattan }}
    </span>
    <span class="badge" :class="driftItems.length ? 'badge-warn' : 'badge-ok'" style="margin-left:0.4rem">
      {{ driftItems.length ? `现网漂移 ${driftItems.length} 处（只标不修）` : '与现网约束一致' }}
    </span>
    <span class="badge badge-bad" style="margin-left:0.4rem">冻结违规 {{ data.violations?.length || 0 }}</span>
    <span class="muted" style="margin-left:0.5rem">方案 #{{ data.id }} · {{ fmtTime(data.created_at) }}</span>
  </div>

  <div v-if="driftItems.length" class="card hs-drift-box">
    <strong>现网漂移（只读标记，历史座位未改动）</strong>
    <ul style="margin:0.4rem 0 0;padding-left:1.1rem">
      <li v-for="(d, i) in driftItems" :key="i">
        <span class="badge badge-warn">{{ d.kind }}</span>
        考生 {{ d.a_id }}<template v-if="d.b_id != null"> / {{ d.b_id }}</template>：{{ d.detail }}
      </li>
    </ul>
  </div>

  <div class="hs-classroom" style="margin-top:0.85rem">
    <aside class="hs-clipboard">
      <h2>考生名册</h2>
      <div v-for="c in candidates" :key="c.id" class="hs-roster-row">
        <div>
          <div>{{ c.name }}</div>
          <div class="hs-ticket">{{ c.ticket_no }}</div>
        </div>
        <div>{{ paperTitle(c.paper_id) }}</div>
      </div>
    </aside>
    <div class="hs-desk-stage" v-if="data">
      <div class="hs-grid-board" :style="gridStyle">
        <div
          v-for="(cell,i) in cells" :key="i"
          class="hs-desk"
          :class="{ empty: cell.empty, 'hs-viol': isViol(cell), 'hs-drift': isDrift(cell), 'hs-now-blocked': !cell.empty && isBlockedNow(cell) }"
        >
          <template v-if="!cell.empty">
            <span class="hs-paper-tag" :class="paperClass(cell.paper_id)">{{ paperTitle(cell.paper_id) }}</span>
            <div>{{ cell.name }}</div>
            <span v-if="isDrift(cell)" class="hs-drift-flag">漂移</span>
          </template>
          <template v-else>
            <span v-if="isBlockedNow(cell)" class="hs-blocked-x">禁</span>
            <span v-else>·</span>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

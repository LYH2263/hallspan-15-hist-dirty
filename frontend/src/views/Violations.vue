<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const viols = ref<any[]>([])
const unplaced = ref<any[]>([])
const drift = ref<any>(null)
const plans = ref<any[]>([])
const selectedId = ref<number | null>(null)

async function load(planId?: number) {
  const q = planId != null ? `plan_id=${planId}` : 'hall_id=1'
  const res = await api(`/seating/violations?${q}`)
  viols.value = res.violations
  unplaced.value = res.unplaced
  drift.value = res.drift
  selectedId.value = res.plan_id
}
onMounted(async () => {
  plans.value = await api('/seating/plans?hall_id=1')
  await load()
})

const isLatest = computed(() => plans.value.length > 0 && selectedId.value === plans.value[0].id)
const driftText = computed(() => {
  const d = drift.value
  if (!d?.has_drift) return ''
  const parts: string[] = []
  if (d.min_manhattan) parts.push(`最小间距 ${d.min_manhattan.then} → ${d.min_manhattan.now}`)
  if (d.blocked_added?.length) parts.push(`新增禁坐 ${d.blocked_added.length} 格`)
  if (d.blocked_removed?.length) parts.push(`取消禁坐 ${d.blocked_removed.length} 格`)
  if (d.paper_changes?.length) parts.push(`套别变更 ${d.paper_changes.length} 人`)
  return parts.join(' · ')
})
</script>

<template>
  <h1>违规</h1>
  <p class="sub">间距不足或同试卷四邻相邻 · 历史方案的违规钉在生成当时</p>

  <div class="hs-plan-bar">
    <select :value="selectedId ?? ''" @change="load(Number(($event.target as HTMLSelectElement).value))">
      <option v-for="p in plans" :key="p.id" :value="p.id">方案 #{{ p.id }} · 最小距 {{ p.min_manhattan }}</option>
    </select>
    <span v-if="isLatest" class="badge badge-ok">当前方案</span>
    <span v-else class="badge badge-warn">历史方案 · 只读</span>
  </div>

  <div v-if="drift?.has_drift" class="hs-drift">
    ⚠ 约束已漂移（仅标记，不重算历史违规）：{{ driftText }}
  </div>

  <div class="card">
    <table>
      <thead><tr><th>类型</th><th>考生A</th><th>考生B</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="(v,i) in viols" :key="i">
          <td>{{ v.kind }}</td><td>{{ v.a_id }}</td><td>{{ v.b_id }}</td><td>{{ v.detail }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!viols.length" class="muted">无违规</p>
  </div>
  <div class="card" v-if="unplaced.length">
    <h3>未排上</h3>
    <div v-for="u in unplaced" :key="u.id">{{ u.name }}（{{ u.ticket_no }}）</div>
  </div>
</template>

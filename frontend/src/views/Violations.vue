<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const planId = ref<number | null>(null)
const plans = ref<any[]>([])
const viols = ref<any[]>([])
const drift = ref<any[]>([])
const unplaced = ref<any[]>([])
const diff = ref<any>(null)

async function loadPlans() {
  plans.value = (await api<{ plans: any[] }>('/seating/plans?hall_id=1')).plans
}
async function openPlan(id: number) {
  planId.value = id
  const res = await api(`/seating/violations?plan_id=${id}`)
  viols.value = res.violations          // 冻结违规：生成当时算出并原样存储
  drift.value = res.drift?.items || []  // 现网漂移：实时标记，绝不入库/重排
  unplaced.value = res.unplaced
  diff.value = res.constraint_diff
}
onMounted(async () => {
  await loadPlans()
  if (plans.value.length) await openPlan(plans.value[0].id)
})
</script>

<template>
  <h1>违规</h1>
  <p class="sub">红色＝方案生成当时的冻结违规；琥珀色＝现网约束与历史不一致的漂移（只标不修）。</p>

  <div class="card">
    <label class="muted" style="font-size:0.82rem">
      历史方案
      <select :value="planId ?? ''" @change="openPlan(Number(($event.target as HTMLSelectElement).value))" style="margin-left:0.4rem">
        <option v-for="p in plans" :key="p.id" :value="p.id">#{{ p.id }}</option>
      </select>
    </label>
    <span v-if="diff?.min_manhattan?.changed" class="badge badge-warn" style="margin-left:0.6rem">
      最小距已变：历史 {{ diff.min_manhattan.stored }} → 现网 {{ diff.min_manhattan.current }}
    </span>
  </div>

  <div class="card">
    <h3 style="margin-top:0">冻结违规 <span class="badge badge-bad">{{ viols.length }}</span></h3>
    <table>
      <thead><tr><th>类型</th><th>考生A</th><th>考生B</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="(v,i) in viols" :key="'v'+i">
          <td><span class="badge badge-bad">{{ v.kind }}</span></td>
          <td>{{ v.a_id }}</td><td>{{ v.b_id }}</td><td>{{ v.detail }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!viols.length" class="muted">无冻结违规</p>
  </div>

  <div class="card hs-drift-box">
    <h3 style="margin-top:0">现网漂移（只读标记，历史未重排） <span class="badge badge-warn">{{ drift.length }}</span></h3>
    <table>
      <thead><tr><th>类型</th><th>考生A</th><th>考生B</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="(d,i) in drift" :key="'d'+i">
          <td><span class="badge badge-warn">{{ d.kind }}</span></td>
          <td>{{ d.a_id }}</td><td>{{ d.b_id }}</td><td>{{ d.detail }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!drift.length" class="muted">与现网约束一致，无漂移</p>
  </div>

  <div class="card" v-if="unplaced.length">
    <h3 style="margin-top:0">未排上</h3>
    <div v-for="u in unplaced" :key="u.id">{{ u.name }}（{{ u.ticket_no }}）</div>
  </div>
</template>

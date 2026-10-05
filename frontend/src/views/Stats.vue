<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const s = ref<any>({})
const plans = ref<any[]>([])
const planId = ref<number | null>(null)

async function loadPlans() {
  plans.value = (await api<{ plans: any[] }>('/seating/plans?hall_id=1')).plans
}
async function openPlan(id: number) {
  planId.value = id
  s.value = await api(`/seating/stats?plan_id=${id}`)
}
onMounted(async () => {
  await loadPlans()
  if (plans.value.length) await openPlan(plans.value[0].id)
})
</script>
<template>
  <h1>统计</h1>
  <p class="sub">以下数字为所选历史方案生成当时的冻结统计；漂移另计，不回写历史。</p>
  <div class="card">
    <label class="muted" style="font-size:0.82rem">
      历史方案
      <select :value="planId ?? ''" @change="openPlan(Number(($event.target as HTMLSelectElement).value))" style="margin-left:0.4rem">
        <option v-for="p in plans" :key="p.id" :value="p.id">#{{ p.id }}</option>
      </select>
    </label>
  </div>
  <div class="card" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
    <div><div class="muted">已排座</div><div class="stat">{{ s.seated }}</div></div>
    <div><div class="muted">未排上</div><div class="stat">{{ s.unplaced }}</div></div>
    <div><div class="muted">冻结违规</div><div class="stat">{{ s.violations }}</div></div>
    <div><div class="muted">座位容量</div><div class="stat">{{ s.capacity }}</div></div>
    <div><div class="muted">现网漂移</div><div class="stat" style="color:var(--hs-paper-b)">{{ s.drift_count }}</div></div>
  </div>
</template>

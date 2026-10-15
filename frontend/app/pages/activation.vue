<script setup lang="ts">
import OperationsModal from "~/components/accounts/OperationsModal.vue";
import { accountPlanInfo, type Account, type AccountGroup } from "~/utils/accounts";

useHead({ title: "开通工作台" });
const { request } = useApi();
const toast = useToast();
const rows = shallowRef<Account[]>([]);
const selected = ref<number[]>([]);
const loading = ref(false);
const error = ref("");
const query = ref("");
const page = ref(1);
const total = ref(0);
const operationOpen = ref(false);
const submitting = ref(false);
const groups = ref<AccountGroup[]>([]);
const eligible = computed(() => rows.value.filter((row) => !!row.access_token));
const selectedRows = computed(() => rows.value.filter((row) => selected.value.includes(row.id)));
const counts = computed(() => ({
  all: total.value,
  ready: rows.value.filter((row) => !!row.access_token).length,
  selected: selected.value.length,
  plus: rows.value.filter((row) => accountPlanInfo(row).paid).length,
}));
async function load() {
  loading.value = true;
  error.value = "";
  try {
    const result = await request("/api/accounts", {
      query: { paged: 1, page: page.value, page_size: 50, archived: 0, q: query.value.trim() },
    });
    rows.value = result.items || [];
    total.value = Number(result.total || 0);
    selected.value = selected.value.filter((id) => rows.value.some((row) => row.id === id));
  } catch (cause: any) {
    error.value = cause?.message || "账号列表加载失败";
  } finally {
    loading.value = false;
  }
}
function toggle(id: number) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((item) => item !== id)
    : [...selected.value, id];
}
function togglePage() {
  const ids = eligible.value.map((row) => row.id);
  selected.value = ids.every((id) => selected.value.includes(id))
    ? selected.value.filter((id) => !ids.includes(id))
    : [...new Set([...selected.value, ...ids])];
}
function openActivation() {
  if (!selected.value.length) return toast.info("请先选择至少一个账号");
  operationOpen.value = true;
}
function submitted() {
  operationOpen.value = false;
  toast.success("开通任务已提交");
  void load();
}
onMounted(() => void load());
</script>

<template>
  <section class="activation-page">
    <div class="activation-heading">
      <div><div class="eyebrow">ACCOUNTS / PLUS</div><h1>开通工作台</h1><p>选择账号并提交 Plus 开通任务，集中查看账号与服务配置。</p></div>
      <div class="heading-actions"><span class="live-state"><i />工作台就绪</span><NuxtLink class="secondary-action" to="/providers">管理服务商</NuxtLink></div>
    </div>
    <div class="notice-list">
      <div class="notice warning"><b>!</b><span>仅对确认符合条件的账号提交开通任务；提链或支付服务可能消耗 CDK 额度。</span></div>
      <div class="notice"><b>i</b><span>Checkout 成功不代表已支付或已开通 Plus，请以账号套餐状态和服务端核验结果为准。</span></div>
    </div>
    <div class="activation-columns">
      <section class="panel setup-panel">
        <header class="panel-heading"><div><h2>提交任务</h2><p>先选择账号，再配置提链与支付服务</p></div><span class="step-mark">01</span></header>
        <div class="metric-row">
          <div><span>账号总数</span><strong>{{ counts.all }}</strong></div>
          <div><span>本页可用</span><strong>{{ counts.ready }}</strong></div>
          <div><span>已选择</span><strong class="accent-number">{{ counts.selected }}</strong></div>
        </div>
        <div class="form-block">
          <div class="block-title"><span>账号选择</span><NuxtLink to="/accounts">账号管理 <span aria-hidden="true">↗</span></NuxtLink></div>
          <div class="search-row"><input v-model="query" aria-label="搜索账号" placeholder="搜索邮箱" @keydown.enter="page = 1; load()" /><button class="icon-action" title="刷新账号" aria-label="刷新账号" @click="load">↻</button></div>
          <div v-if="error" class="inline-error">{{ error }} <button @click="load">重试</button></div>
          <div class="account-list">
            <div v-if="loading" class="empty-state">正在加载账号…</div>
            <div v-else-if="!rows.length" class="empty-state">没有找到账号</div>
            <label v-for="account in rows" :key="account.id" class="account-option" :class="{ disabled: !account.access_token }">
              <input type="checkbox" :disabled="!account.access_token" :checked="selected.includes(account.id)" @change="toggle(account.id)" />
              <span class="account-copy"><strong>{{ account.email }}</strong><small>{{ accountPlanInfo(account).label || '套餐待检查' }}</small></span>
              <span class="token-state" :class="account.access_token ? 'token-ready' : 'token-missing'">{{ account.access_token ? 'AT 可用' : '缺少 AT' }}</span>
            </label>
          </div>
          <div class="list-footer"><span>显示 {{ rows.length }} / {{ total }}</span><button class="text-action" :disabled="page <= 1" @click="page--; load()">上一页</button><button class="text-action" :disabled="page * 50 >= total" @click="page++; load()">下一页</button></div>
        </div>
        <div class="task-summary"><div class="summary-title"><span>当前选择</span><small>可用账号 {{ counts.ready }} 个</small></div><div class="summary-count"><strong>{{ selected.length }}</strong><span>个账号待开通</span></div><p>开通选项将在提交前确认，避免误用服务商或凭据。</p></div>
        <button class="primary-action" :disabled="!selected.length" @click="openActivation"><span>＋</span>配置并提交开通任务</button>
      </section>

      <section class="panel activity-panel">
        <header class="panel-heading"><div><h2>开通概况</h2><p>账号套餐状态与执行入口</p></div><NuxtLink class="text-action" to="/tasks">任务中心 ↗</NuxtLink></header>
        <div class="status-tabs"><span class="active">账号状态 <b>{{ rows.length }}</b></span><button class="icon-action" aria-label="刷新列表" title="刷新列表" @click="load">↻</button></div>
        <div class="overview-list">
          <div class="overview-row"><span class="status-indicator green"/><div><strong>已开通 Plus</strong><small>本页账号当前已识别套餐</small></div><b>{{ counts.plus }}</b></div>
          <div class="overview-row"><span class="status-indicator teal"/><div><strong>可提交开通</strong><small>持有可用 access token</small></div><b>{{ counts.ready }}</b></div>
          <div class="overview-row"><span class="status-indicator amber"/><div><strong>待检查账号</strong><small>建议先检查套餐或刷新账号状态</small></div><b>{{ Math.max(0, rows.length - counts.plus) }}</b></div>
        </div>
        <div class="section-divider"></div>
        <div class="activity-title"><h3>服务配置</h3><NuxtLink to="/providers">查看全部 ↗</NuxtLink></div>
        <div class="service-row"><span class="service-icon extract">↗</span><div><strong>提链服务</strong><small>提交时选择服务商和 CDK</small></div><NuxtLink to="/providers">配置</NuxtLink></div>
        <div class="service-row"><span class="service-icon pay">$</span><div><strong>支付服务</strong><small>支持已保存配置或临时凭据</small></div><NuxtLink to="/settings">配置</NuxtLink></div>
        <div class="result-box"><div class="result-head"><span class="result-pulse"/><strong>运行状态</strong><span class="result-label">就绪</span></div><p>当前工作台已连接账号库。提交后可在任务中心跟踪执行日志与结果。</p><NuxtLink to="/tasks" class="result-link">打开任务中心 <span>→</span></NuxtLink></div>
        <div class="activity-footer"><span>本页已开通</span><strong>{{ counts.plus }} <small>个账号</small></strong><NuxtLink to="/accounts">查看账号</NuxtLink></div>
      </section>
    </div>
    <OperationsModal v-if="operationOpen" :key="`activation-${selected.join('-')}`" action="activate" :accounts="selectedRows" :account-ids="selected" :account-count="selected.length" :groups="groups" @close="operationOpen = false" @submitted="submitted" @changed="load" />
  </section>
</template>

<style scoped>
.activation-page{max-width:1160px;margin:0 auto;color:#263447}.activation-heading{display:flex;justify-content:space-between;align-items:flex-end;margin:4px 0 22px}.eyebrow{font-size:10px;font-weight:700;color:#8994a1;letter-spacing:1px}.activation-heading h1{font-size:25px;line-height:1.25;margin:5px 0 5px}.activation-heading p,.panel-heading p{font-size:12px;color:#7c8794}.heading-actions{display:flex;align-items:center;gap:12px}.live-state{display:flex;align-items:center;gap:7px;color:#5e6a76;font-size:11px}.live-state i,.result-pulse{width:7px;height:7px;border-radius:50%;background:#21a57e;display:inline-block}.secondary-action{font-size:11px;padding:7px 11px;color:#394959;border:1px solid #dfe4e8;border-radius:5px;background:#fff}.notice-list{display:grid;gap:8px;margin-bottom:18px}.notice{display:flex;gap:9px;align-items:center;background:#fff;border:1px solid #e3e7e9;border-radius:6px;padding:9px 11px;font-size:11px;color:#687482}.notice b{color:#188875;border:1px solid #b6ddd4;border-radius:50%;width:16px;height:16px;display:grid;place-items:center;font-size:10px;flex:none}.notice.warning{color:#b86a31;border-color:#f0dfc9}.notice.warning b{color:#cf782e;border-color:#efc99f}.activation-columns{display:grid;grid-template-columns:minmax(330px,.9fr) minmax(420px,1.25fr);gap:14px;align-items:start}.panel{background:#fff;border:1px solid #e0e5e8;border-radius:7px;padding:18px}.panel-heading{display:flex;justify-content:space-between;align-items:flex-start}.panel-heading h2{font-size:15px;margin:0 0 3px}.step-mark{font-size:10px;color:#9aa4ad;font-weight:700}.metric-row{display:grid;grid-template-columns:repeat(3,1fr);padding:15px 0;margin-top:11px;border-top:1px solid #eef0f2;border-bottom:1px solid #eef0f2}.metric-row>div{padding-left:12px;border-left:1px solid #edf0f1}.metric-row>div:first-child{padding-left:0;border:0}.metric-row span,.summary-title,.activity-footer{font-size:10px;color:#7e8995}.metric-row strong{display:block;font-size:19px;color:#243447;line-height:1.4}.metric-row .accent-number{color:#d46a3a}.form-block{margin-top:16px}.block-title,.summary-title,.activity-title{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:650;color:#344253}.block-title a,.activity-title a{font-weight:500;color:#7c8994;font-size:10px}.search-row{display:flex;gap:6px;margin:10px 0 8px}.search-row input{min-width:0;flex:1;border:1px solid #dfe4e7;border-radius:5px;padding:7px 9px;font-size:11px;color:#344253}.icon-action{width:30px;height:30px;border:1px solid #e0e5e8;border-radius:5px;background:#fff;color:#63717d;font-size:17px;line-height:1}.account-list{border:1px solid #e7eaed;border-radius:5px;max-height:290px;overflow:auto}.account-option{min-height:49px;display:flex;align-items:center;gap:9px;padding:7px 9px;border-bottom:1px solid #f0f2f3;cursor:pointer}.account-option:last-child{border-bottom:0}.account-option.disabled{opacity:.55;cursor:not-allowed}.account-option input{width:14px;height:14px;accent-color:#178c78;flex:none}.account-copy{min-width:0;flex:1}.account-copy strong,.account-copy small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.account-copy strong{font-size:10px;font-weight:600;color:#374454}.account-copy small{font-size:9px;color:#929ca6}.token-state{font-size:9px;white-space:nowrap}.token-ready{color:#178c78}.token-missing{color:#c17839}.list-footer{display:flex;align-items:center;gap:9px;padding-top:8px;color:#929ba4;font-size:9px}.list-footer span{margin-right:auto}.text-action{border:0;background:none;color:#5c7880;font-size:10px;padding:4px}.text-action:disabled{opacity:.35}.empty-state{padding:20px;text-align:center;color:#929ca6;font-size:11px}.inline-error{padding:8px;color:#b95345;font-size:10px}.inline-error button{border:0;background:none;color:inherit;text-decoration:underline}.task-summary{margin-top:14px;padding:12px;border:1px solid #f0d3ae;background:#fffaf4;border-radius:5px}.summary-title small{font-weight:400;color:#929ca6}.summary-count{display:flex;align-items:baseline;gap:6px;margin-top:6px}.summary-count strong{font-size:23px;color:#ba6934}.summary-count span{font-size:11px;color:#677482}.task-summary p{font-size:10px;color:#897a6e;margin-top:3px}.primary-action{width:100%;margin-top:10px;height:38px;border:0;border-radius:5px;background:#202a32;color:#fff;font-size:11px;font-weight:600}.primary-action span{font-size:16px;margin-right:5px;vertical-align:-1px}.primary-action:disabled{opacity:.45}.activity-panel{min-height:540px}.status-tabs{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #eceff1;margin-top:17px}.status-tabs>span{padding:9px 4px;border-bottom:2px solid #178d79;color:#294a48;font-size:10px;font-weight:600}.status-tabs b{margin-left:4px;color:#88939e}.overview-list{padding:4px 0}.overview-row{display:flex;align-items:center;gap:10px;padding:13px 4px;border-bottom:1px solid #f0f2f3}.status-indicator{width:8px;height:8px;border-radius:50%;flex:none}.status-indicator.green{background:#24a17e}.status-indicator.teal{background:#3aafa1}.status-indicator.amber{background:#dfa14c}.overview-row div{min-width:0;flex:1}.overview-row strong,.overview-row small{display:block}.overview-row strong{font-size:11px;font-weight:600}.overview-row small{font-size:9px;color:#909aa4}.overview-row>b{font-size:12px;color:#5f6e7b}.section-divider{height:1px;background:#eceff1;margin:6px 0 16px}.activity-title{margin-bottom:7px}.service-row{display:flex;align-items:center;gap:9px;padding:10px 2px;border-top:1px solid #f0f2f3}.service-icon{width:27px;height:27px;border-radius:5px;display:grid;place-items:center;font-size:13px;font-weight:700}.service-icon.extract{background:#edf5f2;color:#208c76}.service-icon.pay{background:#fff3e8;color:#bd7942}.service-row div{min-width:0;flex:1}.service-row strong,.service-row small{display:block}.service-row strong{font-size:10px}.service-row small{font-size:9px;color:#929ca6}.service-row>a:last-child{font-size:9px;color:#178c78}.result-box{margin-top:15px;padding:13px;border:1px solid #b9e4d8;border-radius:5px;background:#f1faf7}.result-head{display:flex;align-items:center;gap:7px;font-size:10px}.result-label{margin-left:auto;color:#14866d;background:#dcf4eb;border-radius:10px;padding:2px 7px;font-size:9px}.result-box p{margin:9px 0;color:#64756f;font-size:10px}.result-link{font-size:10px;color:#15856f}.result-link span{margin-left:4px}.activity-footer{display:flex;align-items:center;gap:8px;margin-top:13px;padding-top:12px;border-top:1px solid #edf0f1}.activity-footer strong{font-size:15px;color:#d36c3a;margin-right:auto}.activity-footer strong small{font-size:9px;font-weight:400;color:#798590}.activity-footer>a{font-size:10px;color:#178c78}@media(max-width:850px){.activation-columns{grid-template-columns:1fr}.activation-heading{align-items:flex-start;gap:12px}.activation-heading p{max-width:400px}.activity-panel{min-height:0}}@media(max-width:560px){.activation-page{padding:0 1px}.activation-heading{display:block}.heading-actions{margin-top:13px}.activation-heading h1{font-size:22px}.panel{padding:14px}.notice{align-items:flex-start}.notice b{margin-top:1px}.activation-columns{gap:10px}}
</style>

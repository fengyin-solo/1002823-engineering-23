<template>
  <section class="page" data-module="seedling">
    <header class="page-head">
      <div>
        <h2>苗木基地管理</h2>
        <p class="page-desc">
          苗木数据走可重复的准备流程：示例数据按培育品种分组导入，自动核对出圃周期与在圃数量，
          数量对不上时以【{{ prepare.authority || '出圃数量' }}】为准，核对不通过不算准备好。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="preparing" @click="runPrepare">
          {{ preparing ? '正在准备…' : '重新执行数据准备' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出苗木基地清单</button>
      </div>
    </header>

    <!-- 接口无响应 / 请求失败的原因：显著横幅，保留在页面上 -->
    <div v-if="errorMessage" class="alert alert-error" role="alert">
      <strong>请求异常：</strong>{{ errorMessage }}
    </div>

    <!-- 数据准备状态面板 -->
    <section class="prepare-panel">
      <div class="prepare-state">
        <span :class="['state-dot', status.ready ? 'state-ok' : 'state-bad']"></span>
        <div>
          <div class="state-title">
            数据准备：{{ status.ran ? (status.ready ? '已就绪' : '未就绪（核对未通过，不算准备好）') : '尚未准备' }}
          </div>
          <div class="state-sub">{{ status.message }}</div>
        </div>
      </div>
      <div class="stat-row prepare-stats">
        <article class="stat-card">
          <span class="stat-label">培育品种</span>
          <strong class="stat-value">{{ status.variety_count ?? '—' }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">苗圃数</span>
          <strong class="stat-value">{{ status.nurseries ?? '—' }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">出圃合计（株）</span>
          <strong class="stat-value">{{ status.total_outplanted ?? '—' }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">在圃合计（株）</span>
          <strong class="stat-value">{{ status.total_in_nursery ?? '—' }}</strong>
        </article>
      </div>
      <div class="prepare-meta">
        <span>数量指纹 checksum：<code>{{ status.checksum ? status.checksum.slice(0, 16) + '…' : '—' }}</code></span>
        <span>口径：以【{{ prepare.authority || '出圃数量' }}】为准</span>
        <span v-if="status.ran_at">最近运行：{{ status.ran_at }}</span>
      </div>
      <div v-if="mismatchCodes.length" class="alert alert-warn">
        <strong>对不上的苗圃编号：</strong>{{ mismatchCodes.join('、') }}
        <span class="alert-link" role="button" @click="loadLog">查看核对日志</span>
      </div>
      <div class="prepare-log-toggle">
        <button class="link" type="button" @click="toggleLog">{{ showLog ? '收起核对日志' : '查看核对日志' }}</button>
      </div>
      <pre v-if="showLog" class="prepare-log">{{ logContent || '暂无日志，点上方"重新执行数据准备"。' }}</pre>
    </section>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(column, row[column]) }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无苗木基地数据，请先执行数据准备</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条苗木基地记录</span>
      <span v-if="!errorMessage" class="foot-hint">出圃周期单位：月</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type PrepareStatus = {
  ready: boolean
  ran?: boolean
  message?: string
  checksum?: string
  variety_count?: number
  nurseries?: number
  total_outplanted?: number
  total_in_nursery?: number
  ran_at?: string
  mismatch_codes?: string[]
  authority?: string
}

const ENDPOINT = '/api/seedling'
const columns = ['苗圃编号', '苗圃名称', '苗圃面积', '培育品种', '出圃周期', '出圃数量', '在圃数量', '计划总量', '管护人员', '苗圃状态']
const actions = ['登记出圃', '休整轮作', '废弃苗圃']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const preparing = ref(false)
const showLog = ref(false)
const logContent = ref('')
const status = ref<PrepareStatus>({ ready: false, ran: false, message: '' })
const prepare = ref<{ authority: string }>({ authority: '出圃数量' })

const mismatchCodes = computed(() => status.value.mismatch_codes ?? [])

const stats = computed(() => [
  { label: '正常苗圃', value: rows.value.filter((r) => r.status === '正常' || r['苗圃状态'] === '正常').length },
  { label: '出圃中苗圃', value: rows.value.filter((r) => r.status === '出圃中' || r['苗圃状态'] === '出圃中').length },
  { label: '休整中苗圃', value: rows.value.filter((r) => r.status === '休整中' || r['苗圃状态'] === '休整中').length },
])

function formatCell(column: string, value: string | number | null): string {
  if (value === null || value === undefined || value === '') return '—'
  if (column === '出圃周期') return `${value} 月`
  return String(value)
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

/** 统一兜底：任何失败原因都留在页面横幅里，不吞掉。 */
function fail(error: unknown, fallback: string) {
  errorMessage.value = error instanceof Error ? error.message : fallback
}

async function loadStatus() {
  try {
    const response = await request(`${ENDPOINT}/prepare/status`)
    if (!response.ok) throw new Error(`准备状态读取失败（HTTP ${response.status}）`)
    const data = (await response.json()) as PrepareStatus
    status.value = data
    if (data.authority) prepare.value.authority = data.authority
  } catch (error) {
    fail(error, '苗木数据准备状态读取失败')
  }
}

async function loadLog() {
  showLog.value = true
  try {
    const response = await request(`${ENDPOINT}/prepare/log`)
    if (!response.ok) throw new Error(`核对日志读取失败（HTTP ${response.status}）`)
    const data = await response.json()
    logContent.value = data.content ?? data.message ?? '暂无核对日志。'
  } catch (error) {
    fail(error, '核对日志读取失败')
  }
}

function toggleLog() {
  if (!showLog.value) void loadLog()
  else showLog.value = false
}

async function runPrepare() {
  preparing.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/prepare/run`, { method: 'POST' })
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(data?.message ? String(data.message) : `数据准备失败（HTTP ${response.status}）`)
    }
    if (data?.report?.authority) prepare.value.authority = data.report.authority
    await Promise.all([loadStatus(), reload()])
    if (showLog.value) await loadLog()
  } catch (error) {
    fail(error, '苗木数据准备失败')
  } finally {
    preparing.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) throw new Error(`苗木基地动作未生效（HTTP ${response.status}），请稍后重试`)
    const data = await response.json().catch(() => null)
    if (data && data.ok === false) throw new Error(String(data.message ?? '苗木基地动作未生效'))
    await reload()
  } catch (error) {
    fail(error, '苗木基地操作失败')
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) throw new Error(`苗圃列表读取失败（HTTP ${response.status}）`)
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    fail(error, '苗木基地列表读取失败')
  }
}

onMounted(() => {
  void Promise.all([loadStatus(), reload()])
})
</script>

<style scoped>
.alert {
  border: 1px solid;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  margin: 10px 0;
}
.alert-error {
  background: #fef3f2;
  border-color: #fda29b;
  color: #b42318;
}
.alert-warn {
  background: #fffaeb;
  border-color: #fedf89;
  color: #b54708;
}
.alert-link {
  margin-left: 8px;
  color: #1f6feb;
  cursor: pointer;
  text-decoration: underline;
}
.prepare-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 14px;
}
.prepare-state {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.state-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}
.state-ok {
  background: #12b76a;
}
.state-bad {
  background: #f04438;
}
.state-title {
  font-weight: 600;
  font-size: 14px;
}
.state-sub {
  color: var(--muted);
  font-size: 12px;
}
.prepare-stats .stat-card {
  padding: 8px 10px;
}
.prepare-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: var(--muted);
  font-size: 12px;
  margin-top: 8px;
}
.prepare-meta code {
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 4px;
}
.prepare-log-toggle {
  margin-top: 8px;
}
.prepare-log {
  margin-top: 8px;
  background: #0b1220;
  color: #d7e0f0;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
}
.foot-hint {
  color: var(--muted);
}
</style>

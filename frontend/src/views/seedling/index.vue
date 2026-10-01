<template>
  <section class="page" data-module="seedling">
    <header class="page-head">
      <div>
        <h2>苗木基地管理</h2>
        <p class="page-desc">示例数据按培育品种分文件，导入前自动核对出圃周期与在圃数量，核对通过才算准备好。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="preparing" @click="runPrepare">
          {{ preparing ? '准备中…' : '重新执行数据准备' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出苗木基地清单</button>
      </div>
    </header>

    <div v-if="apiErrors.length" class="error-banner">
      <div class="error-banner-head">
        <strong>接口异常留痕（{{ apiErrors.length }}）</strong>
        <button class="link" type="button" @click="clearApiErrors">清空</button>
      </div>
      <ul class="error-banner-list">
        <li v-for="(item, index) in apiErrors" :key="index">
          <span class="error-time">{{ item.time }}</span>
          <span class="error-source">{{ item.source }}</span>
          <span>{{ item.reason }}</span>
        </li>
      </ul>
    </div>

    <!-- 数据准备状态：核对不通过时把对不上的苗圃编号列出来，没核过不算准备好 -->
    <article class="prepare-panel" :class="{ ready: prepare.ready, failed: prepare.ready === false && prepareReport }">
      <div class="prepare-head">
        <div>
          <h3>数据准备流水线</h3>
          <p class="page-desc">{{ prepare.ruleText || '在圃数量以「出圃数量」为准：在圃数量 = 培育数量 - 出圃数量' }}</p>
        </div>
        <span class="prepare-badge" :class="prepare.ready ? 'ok' : 'no'">
          {{ prepare.ready ? '已核对通过 · 数据已准备好' : '未准备好' }}
        </span>
      </div>

      <div v-if="prepare.message" class="prepare-message">{{ prepare.message }}</div>

      <div v-if="prepareReport" class="prepare-body">
        <div class="stat-row">
          <article class="stat-card">
            <span class="stat-label">准备总数</span>
            <strong class="stat-value">{{ prepareReport['导入']?.['准备总数'] ?? rows.length }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">培育数量合计</span>
            <strong class="stat-value">{{ prepareReport['数量汇总']?.['培育数量'] ?? 0 }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">出圃数量合计（准）</span>
            <strong class="stat-value">{{ prepareReport['数量汇总']?.['出圃数量'] ?? 0 }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">在圃数量合计</span>
            <strong class="stat-value">{{ prepareReport['数量汇总']?.['在圃数量'] ?? 0 }}</strong>
          </article>
        </div>

        <div class="prepare-meta">
          <span>示例文件：{{ (prepareReport['示例文件'] ?? []).join('、') || '无' }}</span>
          <span>按品种：{{ formatGroups(prepareReport['品种分组']) }}</span>
          <span>核对日志留档：{{ prepareReport['核对日志目录'] }}{{ prepareReport['日志文件'] || '' }}</span>
        </div>

        <div v-if="mismatches.length" class="mismatch-box">
          <h4>核对不通过：以下苗圃编号对不上（本次未导入，不算准备好）</h4>
          <ul>
            <li v-for="(item, index) in mismatches" :key="index">
              <strong>{{ item['苗圃编号'] }}</strong> · {{ item['对不上的项'] }}：{{ item['说明'] }}
            </li>
          </ul>
        </div>
        <div v-else class="mismatch-box ok">
          <h4>核对通过：出圃周期与在圃数量全部自洽</h4>
          <p v-if="prepareReport['去重跳过']?.length">
            去重跳过 {{ prepareReport['去重跳过'].length }} 条重复编号，只认第一次。
          </p>
        </div>

        <details class="log-box">
          <summary>查看最近一次核对日志</summary>
          <pre>{{ logContent || '暂无日志，执行一次数据准备后留档' }}</pre>
        </details>
      </div>
    </article>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>苗圃编号</span>
        <input v-model="keyword" placeholder="按苗圃编号检索" />
      </label>
      <label class="filter-item">
        <span>培育品种</span>
        <input v-model="variety" placeholder="按培育品种检索" />
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { apiErrors, clearApiErrors, describeError, recordApiError } from '@/api/errors'

type Row = Record<string, string | number | null>
type Report = Record<string, any>

const ENDPOINT = '/api/seedling'
const columns = ["苗圃编号", "苗圃名称", "苗圃面积", "培育品种", "出圃周期", "培育数量", "出圃数量", "在圃数量", "管护人员", "苗圃状态"]
const actions = ["登记出圃", "休整轮作", "废弃苗圃"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const variety = ref('')

const preparing = ref(false)
const prepareReport = ref<Report | null>(null)
const logContent = ref('')

const prepare = reactive({
  ready: false,
  message: '',
  ruleText: '',
})

const stats = computed(() => {
  const count = (status: string) => rows.value.filter((row) => row.status === status).length
  return [
    { label: '正常苗圃', value: count('正常') },
    { label: '出圃苗圃', value: count('出圃中') },
    { label: '休整苗圃', value: count('休整中') },
    { label: '已废弃', value: count('已废弃') },
  ]
})

const mismatches = computed(() => prepareReport.value?.['核对不通过'] ?? [])

function formatGroups(groups: Record<string, number> | undefined): string {
  if (!groups) return '无'
  return Object.entries(groups).map(([name, count]) => `${name} ${count}`).join('、')
}

function resetFilters() {
  keyword.value = ''
  variety.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function loadPrepareStatus() {
  try {
    const response = await request(`${ENDPOINT}/preparation`)
    if (!response.ok) return
    const payload: Report = await response.json()
    applyStatus(payload)
  } catch {
    // 无响应原因已经由 request 记录到 apiErrors，横幅会显示
  }
}

function applyStatus(payload: Report) {
  if (!payload) return
  prepareReport.value = payload
  prepare.ready = Boolean(payload.ready)
  prepare.message = String(payload.message ?? '')
  prepare.ruleText = String(payload['数量规则'] ?? '')
}

async function loadLog() {
  try {
    const response = await request(`${ENDPOINT}/preparation/log`)
    if (!response.ok) return
    const payload = await response.json()
    logContent.value = String(payload.content ?? '')
  } catch {
    // 留痕已在 request 内处理
  }
}

async function runPrepare() {
  preparing.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/preparation/run`, { method: 'POST' })
    if (response.status === 503) {
      // 依赖没装好：停在安装这一步，页面上写清楚缺什么、怎么装
      const payload = await response.json()
      const detail = payload.detail ?? {}
      prepare.message = detail.message ?? '依赖检查未通过，已停在安装这一步'
      recordApiError(`${ENDPOINT}/preparation/run`, prepare.message)
      return
    }
    if (!response.ok) {
      throw new Error(await describeError(response))
    }
    const payload: Report = await response.json()
    applyStatus(payload)
    await loadLog()
    await reload()
    if (!payload.ready) {
      errorMessage.value = '核对未通过，数据不算准备好，请查看上面的对不上苗圃编号列表'
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据准备执行失败'
  } finally {
    preparing.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error(await describeError(response))
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '苗木基地操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (variety.value) query.set('variety', variety.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error(await describeError(response))
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '苗木基地列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadPrepareStatus()
  void loadLog()
})
</script>

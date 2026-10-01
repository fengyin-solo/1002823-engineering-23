/** 接口错误留痕：接口无响应 / 返回异常的原因在页面上留一份，刷新后也还在。 */
import { ref } from 'vue'

export interface ApiError {
  time: string
  source: string
  reason: string
}

const STORAGE_KEY = 'seedling-api-errors'
const MAX_KEPT = 20

function readStored(): ApiError[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? (parsed as ApiError[]) : []
  } catch {
    return []
  }
}

export const apiErrors = ref<ApiError[]>(readStored())

export function recordApiError(source: string, reason: string): void {
  const time = new Date().toLocaleString('zh-CN', { hour12: false })
  apiErrors.value = [{ time, source, reason }, ...apiErrors.value].slice(0, MAX_KEPT)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(apiErrors.value))
}

export function clearApiErrors(): void {
  apiErrors.value = []
  localStorage.removeItem(STORAGE_KEY)
}

/** 把 fetch 响应里的错误说明取出来：FastAPI 的 HTTPException detail 可能是字符串或对象。 */
export async function describeError(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json()
    if (payload && typeof payload === 'object') {
      const detail = (payload as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
      if (detail && typeof detail === 'object') {
        const message = (detail as { message?: unknown }).message
        if (typeof message === 'string') return message
      }
    }
  } catch {
    // 响应不是 JSON，回落到状态码说明
  }
  return `接口返回 ${response.status}，数据未更新`
}

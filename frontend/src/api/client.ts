/** 统一请求封装：拼后端地址、抛网络错误、把无响应原因留痕到页面上。 */
import { describeError, recordApiError } from '@/api/errors'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
    .catch((error: unknown) => {
      // 接口无响应（服务没起、网络断开、超时）：原因必须留在页面上
      const detail = error instanceof Error ? error.message : '请求未送达'
      const reason = `接口无响应：${detail}`
      recordApiError(url, reason)
      throw new Error(reason)
    })
    .then(async (response) => {
      if (!response.ok) {
        // HTTP 错误（如依赖缺失 503、参数错误 400）：把后端说明同样留痕
        await recordHttpError(url, response)
      }
      return response
    })
}

async function recordHttpError(url: string, response: Response): Promise<void> {
  const reason = await describeError(response)
  recordApiError(url, reason)
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}

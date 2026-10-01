/** 统一请求封装：拼后端地址、抛网络错误、给页面留一句可读的说明。
 *
 * 重点是把"接口无响应"的原因分清楚并留在 Error.message 里，页面直接展示：
 * - 后端没启动 / 端口不通 / 跨域被拦：fetch 直接 reject（TypeError: Failed to fetch）
 * - 请求超时：AbortError
 * - 服务端有响应但状态码异常：带上 HTTP 状态码与后端 detail
 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const DEFAULT_TIMEOUT_MS = 10000

export class ApiError extends Error {
  status: number | null
  reason: string

  constructor(message: string, opts: { status?: number | null; reason?: string } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = opts.status ?? null
    this.reason = opts.reason ?? 'unknown'
  }
}

function explainNetworkError(error: unknown): ApiError {
  const detail = error instanceof Error ? error.message : String(error)
  // AbortError：超时主动取消；其余 fetch reject 基本都是"连不上"。
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new ApiError('接口请求超时：后端在 10 秒内没有响应，请确认服务是否卡顿或端口是否正确。', {
      reason: 'timeout',
    })
  }
  return new ApiError(
    `接口无响应（${detail}）。通常是后端服务没有启动、端口 ${location.host} 不可达，` +
      '或被跨域策略拦截；请先确认后端 uvicorn 已在 127.0.0.1:8000 运行。',
    { reason: 'network' },
  )
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)

  return fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    signal: controller.signal,
    ...init,
  })
    .catch((error: unknown) => {
      throw explainNetworkError(error)
    })
    .finally(() => clearTimeout(timer))
}

/** 取出后端错误体里的可读 detail（FastAPI 的 4xx 通常是 {detail: ...}）。 */
async function readDetail(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      return String((body as { detail: unknown }).detail)
    }
    if (body && typeof body === 'object' && 'message' in body) {
      return String((body as { message: unknown }).message)
    }
  } catch {
    /* 非 JSON 响应时忽略，退回状态码说明 */
  }
  return ''
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    const detail = await readDetail(response)
    throw new ApiError(
      `接口返回 ${response.status}，数据未更新${detail ? `：${detail}` : '。'}`,
      { status: response.status, reason: 'http' },
    )
  }
  return (await response.json()) as T
}

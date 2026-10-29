import { useUserStore } from '@/stores/user'
import { EventParser, type RunEvent } from './assistantEvents'
export type { RunEvent } from './assistantEvents'

export interface AssistantModel { model_id: string; name: string; provider: string }
export interface AssistantSession { session_id: string; title: string; updated_at: string; created_at: string }
export interface HistoryMessage { role: string; content: string; timestamp?: string }
export interface ConversationRun {
  run_id: string; session_id: string; trace_id: string; status: string; control?: string
  response?: string; error?: string; error_code?: string; message?: string; model_id?: string
  created_at: string; updated_at: string; runtime?: { model_turns?: number; tool_actions?: number; total_tokens?: number }
}
const origin = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
class AssistantApiError extends Error { constructor(message: string, readonly status: number) { super(message) } }
const runKey = (id: string) => `assistant-run:${useUserStore().user?.id || ''}:${id}`
let modelMetadataAvailable = true, runListingAvailable = true

function headers(): Record<string, string> {
  const token = useUserStore().token
  if (!token) throw new Error('请先登录后再使用智能助手')
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}
async function check(response: Response) {
  if (response.ok) return
  const body = await response.json().catch(() => ({}))
  if (response.status === 401) throw new Error('登录已过期，请重新登录后重试')
  if (response.status === 404) throw new AssistantApiError('对话接口或记录不存在，请确认后端已更新并重启', 404)
  if (response.status === 405) throw new AssistantApiError('当前接口不支持此操作', 405)
  throw new Error(body.detail?.message || body.message || (typeof body.detail === 'string' ? body.detail : '') || `助手服务请求失败（${response.status}）`)
}
// Assistant requests always use authenticated real APIs, independent of other pages' mock switches.
async function api<T>(path: string, method = 'GET', body?: unknown, extraHeaders = {}, prefix = '/v1/chat'): Promise<T> {
  const response = await fetch(`${origin}${prefix}${path}`, {
    method, headers: { ...headers(), ...extraHeaders }, body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(20000),
  })
  await check(response)
  const result = await response.json()
  if (result.code !== 200) throw new Error(result.message || '助手服务返回异常')
  return result.data as T
}

export const assistantApi = {
  async capabilities(): Promise<{ items: { name: string; description?: string }[] }> {
    try { return await api('/tools') }
    catch (exc) {
      if (!(exc instanceof AssistantApiError) || exc.status !== 404) throw exc
      return { items: ['current_time', 'market_kline', 'list_backtests', 'backtest_summary'].map(name => ({ name })) }
    }
  },
  async report(path: string) {
    if (!/^\/v1\/backtest\/[A-Za-z0-9_-]{1,64}\/export$/.test(path)) throw new Error('无效的报告下载路径')
    const response = await fetch(`${origin}${path}`, { headers: headers(), signal: AbortSignal.timeout(40000) })
    await check(response)
    if (response.headers.get('content-type')?.includes('application/json')) throw new Error('报告导出失败，请检查回测状态')
    return { blob: await response.blob(), filename: `backtest-${path.split('/')[3]}.csv` }
  },
  async models(): Promise<{ items: AssistantModel[] }> {
    if (modelMetadataAvailable) {
      try { return await api('/models') }
      catch (exc) { if (!(exc instanceof AssistantApiError) || exc.status !== 404) throw exc; modelMetadataAvailable = false }
    }
    // Compatibility with the running phase-3 server; only retain caller-visible display metadata.
    const result = await api<{ items: (AssistantModel & { user_id?: string; is_active: boolean })[] }>('/models?is_active=true', 'GET', undefined, {}, '/v1/model-management')
    const userId = String(useUserStore().user?.id || '')
    const unique = new Map<string, AssistantModel>()
    for (const item of [...result.items].sort((a, b) => Number(!!a.user_id) - Number(!!b.user_id))) {
      if (item.is_active && (!item.user_id || String(item.user_id) === userId)) unique.set(item.model_id, { model_id: item.model_id, name: item.name, provider: item.provider })
    }
    return { items: [...unique.values()] }
  },
  sessions: () => api<{ sessions: AssistantSession[] }>('/sessions'),
  history: (id: string) => api<{ history: HistoryMessage[] }>(`/sessions/${encodeURIComponent(id)}/history?limit=200`),
  rename: (id: string, title: string) => api(`/sessions/${encodeURIComponent(id)}`, 'PUT', { title }),
  remove: (id: string) => api(`/sessions/${encodeURIComponent(id)}`, 'DELETE'),
  async runs(id: string): Promise<{ items: ConversationRun[] }> {
    if (runListingAvailable) {
      try { return await api(`/runs?session_id=${encodeURIComponent(id)}`) }
      catch (exc) {
        // Older servers return 405 for GET on the POST-only collection route.
        if (!(exc instanceof AssistantApiError) || ![404, 405].includes(exc.status)) throw exc
        runListingAvailable = false
      }
    }
    const runId = localStorage.getItem(runKey(id))
    if (!runId) return { items: [] }
    try {
      const run = await api<ConversationRun>(`/runs/${encodeURIComponent(runId)}`)
      return { items: run.session_id === id ? [run] : [] }
    } catch (exc) {
      if (exc instanceof AssistantApiError && exc.status === 404) { localStorage.removeItem(runKey(id)); return { items: [] } }
      throw exc
    }
  },
  async submit(body: { message: string; session_id?: string; model_id: string; thinking_mode: string }, key: string) {
    const result = await api<{ run: ConversationRun }>('/runs', 'POST', body, { 'Idempotency-Key': key })
    localStorage.setItem(runKey(result.run.session_id), result.run.run_id)
    return result
  },
  run: (id: string) => api<ConversationRun>(`/runs/${encodeURIComponent(id)}`),
  control: (id: string, action: 'cancel' | 'pause' | 'resume') => api<ConversationRun>(`/runs/${encodeURIComponent(id)}/${action}`, 'POST'),
  async events(id: string, cursor: string, signal: AbortSignal, onEvent: (event: RunEvent) => void) {
    const response = await fetch(`${origin}/v1/chat/runs/${encodeURIComponent(id)}/events`, {
      headers: { ...headers(), ...(cursor ? { 'Last-Event-ID': cursor } : {}) }, signal,
    })
    await check(response)
    if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) throw new Error('助手事件连接不可用')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const parser = new EventParser(onEvent)
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) { parser.push(decoder.decode()); break }
        parser.push(decoder.decode(value, { stream: true }))
      }
    } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  },
}


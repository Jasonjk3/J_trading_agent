import { test, beforeEach, afterEach } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'vite'
import { fileURLToPath } from 'node:url'

const output = await build({
  configFile: false, logLevel: 'silent',
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('http://assistant.test'), 'import.meta.env.VITE_USE_MOCK': JSON.stringify('true') },
  plugins: [{ name: 'test-user', resolveId(id) { if (id === '@/stores/user') return '\0test-user' },
    load(id) { if (id === '\0test-user') return 'export const useUserStore = () => globalThis.assistantTestUser' } }],
  build: { write: false, minify: false, lib: { entry: fileURLToPath(new URL('../src/api/assistant.ts', import.meta.url)), formats: ['es'], fileName: 'assistant' } },
})
const parserOutput = await build({ configFile: false, logLevel: 'silent', build: { write: false, minify: false,
  lib: { entry: fileURLToPath(new URL('../src/api/assistantEvents.ts', import.meta.url)), formats: ['es'], fileName: 'parser' } } })
const load = async code => import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}#${crypto.randomUUID()}`)
const builtCode = result => (Array.isArray(result) ? result[0] : result).output.find(item => item.type === 'chunk').code
const { EventParser } = await load(builtCode(parserOutput))
const client = async () => (await load(builtCode(output))).assistantApi
const originalFetch = globalThis.fetch
const originalStorage = globalThis.localStorage
const ok = data => new Response(JSON.stringify({ code: 200, data }), { headers: { 'Content-Type': 'application/json' } })
beforeEach(() => {
  globalThis.assistantTestUser = { token: 'test-token', user: { id: 'owner' } }
  const entries = new Map()
  globalThis.localStorage = { getItem: key => entries.get(key) || null, setItem: (key, value) => entries.set(key, value), removeItem: key => entries.delete(key) }
})
afterEach(() => { globalThis.fetch = originalFetch; globalThis.localStorage = originalStorage; delete globalThis.assistantTestUser })

test('SSE handles split CRLF, multiline data and heartbeats without duplicate delivery', () => {
  const events = []
  const parser = new EventParser(event => events.push(event))
  const wire = ': heartbeat\r\nid: 17\r\nevent: run.succeeded\r\ndata: {"response":\r\ndata: "真实回答"}\r\n\r\n'
  for (const char of wire) parser.push(char)
  parser.push(': ping\n\n')
  assert.deepEqual(events, [{ id: '17', type: 'run.succeeded', data: { response: '真实回答' } }])
})

test('real authenticated submit works even when the other pages enable mocks', async () => {
  const api = await client()
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'http://assistant.test/v1/chat/runs')
    assert.equal(options.headers.Authorization, 'Bearer test-token')
    assert.equal(options.headers['Idempotency-Key'], 'retry-key')
    assert.equal(JSON.parse(options.body).message, '真实请求')
    return ok({ run: { run_id: 'run-1', session_id: 'session-1', status: 'queued' } })
  }
  const result = await api.submit({ message: '真实请求', model_id: 'configured-model', thinking_mode: 'normal' }, 'retry-key')
  assert.equal(result.run.status, 'queued')
  assert.equal(localStorage.getItem('assistant-run:owner:session-1'), 'run-1')
})

test('model fallback keeps owner/shared display metadata and gives private models precedence', async () => {
  const api = await client()
  let count = 0
  globalThis.fetch = async url => {
    if (++count === 1) return new Response('{}', { status: 404 })
    assert.equal(url, 'http://assistant.test/v1/model-management/models?is_active=true')
    return ok({ items: [
      { model_id: 'same', name: 'Shared', provider: 'unit', is_active: true },
      { model_id: 'same', name: 'Mine', provider: 'unit', is_active: true, user_id: 'owner', api_config_id: 12 },
      { model_id: 'other', name: 'Other', provider: 'unit', is_active: true, user_id: 'other' },
      { model_id: 'off', name: 'Off', provider: 'unit', is_active: false },
    ] })
  }
  assert.deepEqual((await api.models()).items, [{ model_id: 'same', name: 'Mine', provider: 'unit' }])
})

test('authorization errors never fall back to another model endpoint', async () => {
  const api = await client()
  let count = 0
  globalThis.fetch = async () => { count++; return new Response('{}', { status: 401 }) }
  await assert.rejects(api.models(), /登录已过期/)
  assert.equal(count, 1)
})

test('tool capabilities come from the running server and older servers expose only their four tools', async () => {
  const api = await client()
  globalThis.fetch = async () => ok({ items: [{ name: 'list_positions' }] })
  assert.deepEqual((await api.capabilities()).items, [{ name: 'list_positions' }])
  globalThis.fetch = async () => new Response('{}', { status: 404 })
  const legacy = await api.capabilities()
  assert.equal(legacy.items.length, 4)
  assert.ok(!legacy.items.some(item => item.name === 'list_positions'))
})

test('report downloads attach authentication and reject external or traversing paths', async () => {
  const api = await client()
  let calls = 0
  globalThis.fetch = async (url, options) => {
    calls++
    assert.equal(url, 'http://assistant.test/v1/backtest/test-id/export')
    assert.equal(options.headers.Authorization, 'Bearer test-token')
    return new Response('time,equity\n1,100', { headers: { 'Content-Type': 'text/csv' } })
  }
  assert.equal((await api.report('/v1/backtest/test-id/export')).filename, 'backtest-test-id.csv')
  for (const path of ['https://other.example/export', '/v1/backtest/../export', '/v1/backtest/x/export?token=bad']) await assert.rejects(api.report(path), /无效/)
  assert.equal(calls, 1)
})

test('old server restores only the current user and session run pointer', async () => {
  const api = await client()
  localStorage.setItem('assistant-run:owner:session-1', 'run-1')
  globalThis.fetch = async url => url.includes('?') ? new Response('{}', { status: 405 }) : ok({ run_id: 'run-1', session_id: 'session-1', status: 'running' })
  assert.equal((await api.runs('session-1')).items[0].run_id, 'run-1')
  globalThis.assistantTestUser.user.id = 'other'
  assert.deepEqual((await api.runs('session-1')).items, [])
})

test('event stream decodes Chinese split across bytes and carries the resume cursor', async () => {
  const api = await client()
  const bytes = new TextEncoder().encode('id: 22\nevent: run.succeeded\ndata: {"response":"北京时间"}\n\n')
  globalThis.fetch = async (url, options) => {
    assert.ok(url.endsWith('/runs/run-1/events'))
    assert.equal(options.headers['Last-Event-ID'], '21')
    assert.equal(options.headers.Authorization, 'Bearer test-token')
    return new Response(new ReadableStream({ start(controller) {
      for (let i = 0; i < bytes.length; i++) controller.enqueue(bytes.slice(i, i + 1))
      controller.close()
    } }), { headers: { 'Content-Type': 'text/event-stream' } })
  }
  const events = []
  await api.events('run-1', '21', new AbortController().signal, event => events.push(event))
  assert.equal(events.length, 1)
  assert.equal(events[0].data.response, '北京时间')
})

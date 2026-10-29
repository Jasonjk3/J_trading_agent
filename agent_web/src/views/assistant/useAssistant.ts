import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assistantApi, type AssistantModel, type ConversationRun, type RunEvent } from '@/api/assistant'
import { useUserStore } from '@/stores/user'

export interface Message { id: string; role: 'user' | 'assistant'; text: string; time: number; deep?: boolean; references?: string[]; error?: boolean }
interface Conversation { id: string; title: string; updatedAt: number; messages: Message[]; draft: string; references: string[]; deep: boolean; saved: boolean; submission?: { fingerprint: string; key: string } }
const terminal = (run: ConversationRun) => ['succeeded', 'failed', 'cancelled'].includes(run.status)
export const referenceOptions = [
  { id: 'positions', label: '账户持仓', description: '查询当前账号授权账户的余额、持仓与名义敞口' },
  { id: 'market', label: '公开行情', description: '按问题查询实时行情 K 线，返回数据时间' },
  { id: 'backtest', label: '我的回测', description: '查询当前登录账号的回测任务与摘要' },
]
export function useAssistant() {
  const conversations = ref<Conversation[]>([])
  const activeId = ref('')
  const active = computed(() => conversations.value.find(item => item.id === activeId.value))
  const query = ref(''), model = ref(''), historyOpen = ref(false), referencesOpen = ref(false)
  const input = ref<HTMLTextAreaElement>(), messageArea = ref<HTMLElement>()
  const models = ref<AssistantModel[]>([]), loading = ref(true), loadingHistory = ref(false), submitting = ref(false)
  const error = ref(''), progress = ref(''), currentRun = ref<ConversationRun | null>(null)
  const toolNames = ref<string[]>([])
  const supportsPositions = computed(() => toolNames.value.includes('list_positions'))
  const enabledReferences = computed(() => referenceOptions.filter(item => item.id !== 'positions' || supportsPositions.value))
  const pending = computed(() => currentRun.value && !terminal(currentRun.value) ? { conversationId: currentRun.value.session_id } : null)
  const paused = computed(() => currentRun.value?.status === 'paused')
  const storageKey = `assistant-session:${useUserStore().user?.id || ''}`
  let alive = true, selection = 0, watchVersion = 0, controller: AbortController | undefined
  const prompts = computed(() => [
    supportsPositions.value ? { title: '分析持仓风险', text: '请先列出我可用的交易所账户；只有一个时查询该账户持仓与名义敞口，多个账户时请让我选择。说明数据环境、时间与未覆盖的风险。', topic: 'positions' } : { title: '查询北京时间', text: '请调用工具查询当前北京时间。', topic: 'time' },
    { title: '解读市场趋势', text: '请查询 BTC-USDT 最近 30 根 1 小时 K 线，结合数据时间解读趋势与风险。', topic: 'market' },
    { title: '复盘策略表现', text: '请查询我最近 1 项回测，分析状态、收益与最大回撤；没有数据请明确说明。', topic: 'backtest' },
  ])
  const groups = computed(() => {
    const today = new Date().setHours(0, 0, 0, 0)
    const filtered = [...conversations.value].filter(item => item.title.toLowerCase().includes(query.value.toLowerCase().trim())).sort((a, b) => b.updatedAt - a.updatedAt)
    return [{ label: '今天', items: filtered.filter(item => item.updatedAt >= today) }, { label: '昨天', items: filtered.filter(item => item.updatedAt < today && item.updatedAt >= today - 86400000) }, { label: '更早', items: filtered.filter(item => item.updatedAt < today - 86400000) }].filter(group => group.items.length)
  })
  const messageError = (exc: unknown) => exc instanceof Error ? exc.message : '助手服务暂时不可用，请稍后重试'
  const referenceLabel = (id: string) => referenceOptions.find(item => item.id === id)?.label ?? id
  const timeLabel = (time: number) => new Date(time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  async function scrollToBottom() { await nextTick(); if (messageArea.value) messageArea.value.scrollTop = messageArea.value.scrollHeight }
  function stopWatching() { watchVersion++; controller?.abort(); controller = undefined }
  function addMessage(conversation: Conversation, role: Message['role'], text: string, extra: Partial<Message> = {}) {
    conversation.messages.push({ id: crypto.randomUUID(), role, text, time: Date.now(), ...extra })
  }
  function showFinal(conversation: Conversation, run: ConversationRun) {
    if (conversation.messages.some(message => message.id === `run:${run.run_id}`)) return
    if (run.status === 'succeeded') addMessage(conversation, 'assistant', run.response || '助手未返回内容', { id: `run:${run.run_id}`, deep: conversation.deep })
    else addMessage(conversation, 'assistant', run.status === 'cancelled' ? '本次生成已停止。' : `生成失败：${run.error || run.error_code || '请检查模型配置后重试'}`, { id: `run:${run.run_id}`, error: run.status === 'failed' })
    conversation.updatedAt = Date.now()
    void scrollToBottom()
  }
  async function watchRun(conversation: Conversation, initial: ConversationRun) {
    stopWatching()
    const version = watchVersion
    let cursor = '', failures = 0
    currentRun.value = initial
    if (terminal(initial)) { showFinal(conversation, initial); return }
    while (alive && version === watchVersion && currentRun.value && !terminal(currentRun.value)) {
      if (currentRun.value.status === 'paused') { progress.value = '任务已暂停，可继续或停止'; return }
      controller = new AbortController()
      const streamController = controller
      // Periodically verify status even if an intermediary stalls the event connection.
      const timeout = setTimeout(() => streamController.abort(), 25000)
      let streamError: unknown
      try {
        await assistantApi.events(initial.run_id, cursor, streamController.signal, (event: RunEvent) => {
          if (version !== watchVersion) return
          if (event.id) cursor = event.id
          const labels: Record<string, string> = { 'run.queued': '任务已提交，等待执行', 'run.started': '模型正在分析', 'model.started': '模型正在分析', 'model.completed': '模型已返回，正在处理结果', 'tool.started': '正在查询真实数据', 'tool.completed': '数据查询已完成，正在整理回答' }
          progress.value = labels[event.type] || '助手正在处理，请稍候'
          if (event.type.startsWith('run.') && ['succeeded', 'failed', 'cancelled', 'paused'].includes(event.type.slice(4))) {
            currentRun.value = { ...currentRun.value!, ...event.data, status: event.type.slice(4) }
            if (terminal(currentRun.value)) showFinal(conversation, currentRun.value)
            streamController.abort()
          }
        })
      } catch (exc) { streamError = exc }
      finally { clearTimeout(timeout) }
      if (!alive || version !== watchVersion) return
      try {
        const latest = await assistantApi.run(initial.run_id)
        if (!alive || version !== watchVersion) return
        currentRun.value = latest
        failures = 0; error.value = ''
        if (terminal(currentRun.value)) {
          showFinal(conversation, currentRun.value)
          if (currentRun.value.status === 'succeeded') {
            try {
              const history = await assistantApi.history(conversation.id)
              if (!alive || version !== watchVersion) return
              conversation.messages = history.history.filter(item => ['user', 'assistant'].includes(item.role)).map(item => ({
                id: crypto.randomUUID(), role: item.role as Message['role'], text: item.content, time: item.timestamp ? Date.parse(item.timestamp) : Date.now(),
              }))
              void scrollToBottom()
            } catch { if (alive && version === watchVersion) error.value = '回答已生成，但历史同步失败，请重新连接' }
          }
          return
        }
        progress.value = currentRun.value.status === 'paused' ? '任务已暂停，可继续或停止' : '任务仍在执行，正在重新连接'
      } catch (exc) {
        if (!alive || version !== watchVersion) return
        if (currentRun.value && terminal(currentRun.value)) { error.value = '已收到执行结果，但状态同步失败，请重新连接'; return }
        if (++failures >= 3) { error.value = `${messageError(exc || streamError)}。任务可能仍在执行，请点击重新连接。`; return }
      }
      await new Promise(resolve => setTimeout(resolve, 1000))
    }
  }
  async function selectConversation(id: string) {
    if (submitting.value) return
    stopWatching(); const version = ++selection
    activeId.value = id; currentRun.value = null; error.value = ''; referencesOpen.value = false; historyOpen.value = false
    const conversation = active.value
    if (!conversation?.saved) { loadingHistory.value = false; return }
    localStorage.setItem(storageKey, id)
    loadingHistory.value = true
    try {
      const [history, runs] = await Promise.all([assistantApi.history(id), assistantApi.runs(id)])
      if (!alive || version !== selection) return
      conversation.messages = history.history.filter(item => ['user', 'assistant'].includes(item.role)).map(item => ({
        id: crypto.randomUUID(), role: item.role as Message['role'], text: item.content, time: item.timestamp ? Date.parse(item.timestamp) : conversation.updatedAt,
      }))
      const latest = runs.items[0]
      currentRun.value = latest || null
      if (latest && latest.status !== 'succeeded') {
        if (latest.message) addMessage(conversation, 'user', latest.message, { time: Date.parse(latest.created_at) })
        if (terminal(latest)) showFinal(conversation, latest)
        else { progress.value = '正在恢复任务连接'; void watchRun(conversation, latest) }
      }
      await scrollToBottom()
    } catch (exc) { if (version === selection) error.value = messageError(exc) }
    finally { if (version === selection) loadingHistory.value = false }
  }
  function newConversation() {
    if (loading.value || submitting.value) return
    const empty = conversations.value.find(item => !item.saved && !item.messages.length && !item.draft)
    if (empty) { void selectConversation(empty.id); return }
    const conversation: Conversation = { id: crypto.randomUUID(), title: '新对话', updatedAt: Date.now(), messages: [], draft: '', references: [], deep: true, saved: false }
    conversations.value.unshift(conversation); void selectConversation(conversation.id)
    void nextTick(() => input.value?.focus())
  }
  async function initialize() {
    loading.value = true; error.value = ''
    try {
      const [available, history, capabilities] = await Promise.all([assistantApi.models(), assistantApi.sessions(), assistantApi.capabilities()])
      if (!alive) return
      models.value = available.items
      toolNames.value = capabilities.items.map(item => item.name)
      model.value = models.value.find(item => item.model_id === 'deepseek-v4.1-flash')?.model_id || models.value[0]?.model_id || ''
      conversations.value = history.sessions.map(item => ({ id: item.session_id, title: item.title || '新对话', updatedAt: Date.parse(item.updated_at || item.created_at), messages: [], draft: '', references: [], deep: true, saved: true }))
      loading.value = false
      const previous = localStorage.getItem(storageKey)
      if (conversations.value.length) await selectConversation(conversations.value.find(item => item.id === previous)?.id || conversations.value[0].id)
      else newConversation()
      if (!models.value.length) error.value = '没有可用模型，请在模型管理中启用模型及其 API 配置'
    } catch (exc) { error.value = messageError(exc) }
    finally { loading.value = false }
  }
  function toggleReference(id: string) {
    if (!active.value) return
    active.value.references = active.value.references.includes(id) ? active.value.references.filter(item => item !== id) : [...active.value.references, id]
    if (active.value.draft.endsWith('@')) active.value.draft = active.value.draft.slice(0, -1)
  }
  function onInput() { if (active.value?.draft.endsWith('@')) referencesOpen.value = true }
  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') referencesOpen.value = false
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); void send() }
  }
  function usePrompt(prompt: { title: string; text: string; topic: string }) {
    if (!active.value || pending.value || submitting.value || loadingHistory.value) return
    active.value.draft = prompt.text
    active.value.references = enabledReferences.value.some(item => item.id === prompt.topic) ? [prompt.topic] : []
    void send()
  }
  async function send() {
    const conversation = active.value
    if (!conversation || !conversation.draft.trim() || pending.value || submitting.value || loadingHistory.value || !model.value) return
    const text = conversation.draft.trim()
    const references = [...conversation.references]
    const message = references.length ? `${text}\n\n请按需使用只读工具查询以下数据：${references.map(referenceLabel).join('、')}。缺少数据请明确说明。` : text
    submitting.value = true; error.value = ''; referencesOpen.value = false
    try {
      const payload = { message, session_id: conversation.saved ? conversation.id : undefined, model_id: model.value, thinking_mode: conversation.deep ? 'deep' : 'normal' }
      const fingerprint = JSON.stringify(payload)
      if (conversation.submission?.fingerprint !== fingerprint) conversation.submission = { fingerprint, key: crypto.randomUUID() }
      const result = await assistantApi.submit(payload, conversation.submission!.key)
      if (!alive) return
      conversation.id = result.run.session_id; conversation.saved = true; activeId.value = conversation.id
      localStorage.setItem(storageKey, conversation.id)
      if (conversation.title === '新对话') conversation.title = text.slice(0, 40)
      conversation.updatedAt = Date.now(); conversation.draft = ''; conversation.submission = undefined
      addMessage(conversation, 'user', message)
      progress.value = '任务已提交，等待执行'
      void scrollToBottom(); void watchRun(conversation, result.run)
    } catch (exc) { error.value = messageError(exc) }
    finally { submitting.value = false }
  }
  async function stopGeneration() {
    if (!currentRun.value) return
    const runId = currentRun.value.run_id
    try {
      const result = await assistantApi.control(runId, 'cancel')
      if (currentRun.value?.run_id !== runId || !alive) return
      currentRun.value = result
      if (terminal(result) && active.value) { stopWatching(); showFinal(active.value, result) }
      else progress.value = '正在停止任务…'
    }
    catch (exc) { error.value = messageError(exc) }
  }
  async function reconnect() { if (active.value?.saved) await selectConversation(active.value.id); else await initialize() }
  async function resumeGeneration() {
    if (!currentRun.value || !active.value) return
    const runId = currentRun.value.run_id
    try { const run = await assistantApi.control(runId, 'resume'); if (alive && currentRun.value?.run_id === runId && active.value) void watchRun(active.value, run) }
    catch (exc) { error.value = messageError(exc) }
  }
  async function copyMessage(message: Message) {
    try { await navigator.clipboard.writeText(message.text); ElMessage.success('已复制回答') }
    catch { ElMessage.error('复制失败，请手动选择文本复制') }
  }
  async function handleHistoryCommand(command: string, item: Conversation) {
    if (submitting.value) return
    try {
      if (command === 'rename') {
        const result = await ElMessageBox.prompt('为这段对话起一个名字', '重命名对话', { inputValue: item.title, inputValidator: value => !!value?.trim() && value.trim().length <= 40 || '请输入 1–40 个字符', confirmButtonText: '保存', cancelButtonText: '取消' })
        if (typeof result === 'object') { if (item.saved) await assistantApi.rename(item.id, result.value.trim()); item.title = result.value.trim() }
      } else if (command === 'delete') {
        if (item.id === currentRun.value?.session_id && pending.value) { ElMessage.info('请先停止当前任务，再删除对话'); return }
        await ElMessageBox.confirm('删除这段对话？', '删除对话', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
        if (item.saved) {
          const runs = await assistantApi.runs(item.id)
          if (runs.items.some(run => !terminal(run))) { ElMessage.info('该对话仍有任务在执行，请先打开并停止任务'); return }
          await assistantApi.remove(item.id)
        }
        conversations.value = conversations.value.filter(value => value.id !== item.id)
        if (activeId.value === item.id) { if (conversations.value.length) await selectConversation(conversations.value[0].id); else newConversation() }
      }
    } catch (exc) { if (exc !== 'cancel' && exc !== 'close') error.value = messageError(exc) }
  }
  onMounted(initialize)
  onUnmounted(() => { alive = false; selection++; stopWatching() })
  return { conversations, activeId, active, query, model, models, historyOpen, referencesOpen, input, messageArea, pending, prompts, groups,
    loading, loadingHistory, submitting, error, progress, currentRun, paused, supportsPositions, referenceOptions: enabledReferences, referenceLabel, timeLabel,
    selectConversation, newConversation, toggleReference, onInput, onKeydown, usePrompt, send, stopGeneration, resumeGeneration, reconnect, copyMessage, handleHistoryCommand }
}

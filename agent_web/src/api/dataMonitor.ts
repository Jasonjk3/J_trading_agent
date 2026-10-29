import { request } from './request'

export type MonitorMetric = 'price' | 'change' | 'volume' | 'rsi'
export type MonitorOperator = '>' | '<' | 'cross_up' | 'cross_down'
export type MonitorRuleType = 'threshold' | 'scheduled' | 'movement'

export interface MonitorRuleOptions {
  ruleType: MonitorRuleType
  windowMinutes: number | null
  movementUnit: 'amount' | 'percent' | null
  movementDirection: 'either' | 'up' | 'down' | null
  startTime: string | null
  endTime: string | null
  reportIntervalMinutes: number | null
}

export interface MonitorRule extends MonitorRuleOptions {
  id: string
  name: string
  description: string
  metric: MonitorMetric
  operator: MonitorOperator
  threshold: number
  system: boolean
  usage: number
}

export interface MonitorTemplate {
  id: string
  name: string
  messageType: 'text' | 'card'
  title: string
  content: string
  system: boolean
  usage: number
}

export interface MonitorTaskPayload extends MonitorRuleOptions {
  name: string
  exchange: 'OKX'
  symbol: string
  frequencySeconds: 10 | 60 | 300
  ruleId: string | null
  metric: MonitorMetric
  operator: MonitorOperator
  threshold: number
  pushConfigId: string
  templateId: string
  cooldownSeconds: 300 | 900 | 3600
  recoveryNotice: boolean
  enabled: boolean
}

export interface MonitorTask extends MonitorTaskPayload {
  id: string
  ruleName: string
  channelName: string
  templateName: string
  lastValue: number | null
  lastCheckedAt: string | null
  lastTriggeredAt: string | null
  lastError: string | null
}

export interface MonitorEvent {
  id: string
  taskId: string
  eventType: 'trigger' | 'recovery' | 'report'
  value: number
  success: boolean
  error: string | null
  createdAt: string
}

const base = '/v1/data-monitor'
export const dataMonitorApi = {
  rules: () => request.get<{ list: MonitorRule[] }>(`${base}/rules`),
  createRule: (data: Omit<MonitorRule, 'id' | 'system' | 'usage'>) => request.post<MonitorRule>(`${base}/rules`, data),
  deleteRule: (id: string) => request.delete(`${base}/rules/${id}`),
  templates: () => request.get<{ list: MonitorTemplate[] }>(`${base}/templates`),
  createTemplate: (data: Omit<MonitorTemplate, 'id' | 'system' | 'usage'>) => request.post<MonitorTemplate>(`${base}/templates`, data),
  deleteTemplate: (id: string) => request.delete(`${base}/templates/${id}`),
  tasks: () => request.get<{ list: MonitorTask[] }>(`${base}/tasks`),
  createTask: (data: MonitorTaskPayload) => request.post<{ id: string }>(`${base}/tasks`, data),
  updateTask: (id: string, data: MonitorTaskPayload) => request.put<{ id: string }>(`${base}/tasks/${id}`, data),
  setEnabled: (id: string, enabled: boolean) => request.put(`${base}/tasks/${id}/enabled`, { enabled }),
  deleteTask: (id: string) => request.delete(`${base}/tasks/${id}`),
  events: (taskId?: string) => request.get<{ list: MonitorEvent[] }>(`${base}/events`, { params: { taskId } }),
  summary: () => request.get<{ todayTriggers: number; pushSuccessRate: number | null }>(`${base}/summary`),
}

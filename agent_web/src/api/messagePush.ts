import { request } from './request'

export type BotType = 'webhook' | 'app'
export type ReceiveType = 'chat_id' | 'open_id' | 'user_id' | 'email'
export type TestStatus = 'never' | 'success' | 'failed'

export interface MessagePushConfig {
  id: string
  botType: BotType
  name: string
  description: string
  enabled: boolean
  webhookMasked: string
  hasSecret: boolean
  appIdMasked: string
  hasAppSecret: boolean
  receiveType?: ReceiveType
  receiveIdMasked: string
  lastTestStatus: TestStatus
  lastTestAt?: string
  lastError?: string
  createdAt: string
  updatedAt?: string
}

export interface MessagePushListResponse {
  list: MessagePushConfig[]
  total: number
}

export interface MessagePushConfigPayload {
  botType: BotType
  name: string
  description?: string
  webhook?: string
  secret?: string
  appId?: string
  appSecret?: string
  receiveType?: ReceiveType
  receiveId?: string
  enabled: boolean
}

export interface ValidatePayload {
  botType: BotType
  webhook?: string
  secret?: string
  appId?: string
  appSecret?: string
}

export interface TestMessagePayload {
  messageType: 'text' | 'card'
  title?: string
  content: string
  receiveType?: ReceiveType
  receiveId?: string
}

export interface OperationResult {
  success: boolean
  message: string
}

export const messagePushApi = {
  getList(): Promise<MessagePushListResponse> {
    return request.get('/v1/message-push-configs') as Promise<MessagePushListResponse>
  },
  create(data: MessagePushConfigPayload): Promise<MessagePushConfig> {
    return request.post('/v1/message-push-configs', data) as Promise<MessagePushConfig>
  },
  update(id: string, data: Partial<MessagePushConfigPayload>): Promise<MessagePushConfig> {
    return request.put(`/v1/message-push-configs/${id}`, data) as Promise<MessagePushConfig>
  },
  remove(id: string): Promise<void> {
    return request.delete(`/v1/message-push-configs/${id}`) as Promise<void>
  },
  validateDraft(data: ValidatePayload): Promise<OperationResult> {
    return request.post('/v1/message-push-configs/validate', data) as Promise<OperationResult>
  },
  validateSaved(id: string): Promise<OperationResult> {
    return request.post(`/v1/message-push-configs/${id}/validate`) as Promise<OperationResult>
  },
  sendTest(id: string, data: TestMessagePayload): Promise<OperationResult> {
    return request.post(`/v1/message-push-configs/${id}/test`, data) as Promise<OperationResult>
  },
}

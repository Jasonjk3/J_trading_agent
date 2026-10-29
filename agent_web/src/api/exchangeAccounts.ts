import { request } from './request'

/** 支持的交易所标识 */
export type ExchangeCode = 'okx'

/** 绑定/校验状态 */
export type BindStatus = 'success' | 'failed' | 'pending' | 'never'

/** 交易所配置列表项（与后端对齐，Secret 仅脱敏展示） */
export interface ExchangeAccountListItem {
  id: string
  exchange: ExchangeCode
  remark?: string
  bindStatus: BindStatus
  lastVerifiedAt?: string
  enabled: boolean
  readOnly?: boolean
  /** 脱敏后的 API Key，如 ****xxxx */
  apiKeyMasked?: string
  /** 是否需要 Passphrase（如 OKX） */
  hasPassphrase?: boolean
  createdAt: string
  updatedAt?: string
}

/** 列表查询参数 */
export interface ExchangeAccountListParams {
  exchange?: ExchangeCode
  enabled?: boolean
  bindStatus?: BindStatus
}

/** 列表响应 */
export interface ExchangeAccountListRes {
  list: ExchangeAccountListItem[]
  total: number
}

/** 新增/编辑表单（密钥仅提交时使用，不持久化到前端） */
export interface CreateExchangeAccountDto {
  exchange: ExchangeCode
  apiKey: string
  apiSecret: string
  passphrase?: string
  remark?: string
  readOnly?: boolean
  enabled?: boolean
}

export interface UpdateExchangeAccountDto {
  apiKey?: string
  apiSecret?: string
  passphrase?: string
  remark?: string
  readOnly?: boolean
  enabled?: boolean
}

/** 校验连接响应 */
export interface VerifyResult {
  success: boolean
  message?: string
}

export const exchangeAccountsApi = {
  getList(params?: ExchangeAccountListParams): Promise<ExchangeAccountListRes> {
    return request.get('/v1/exchange-accounts', { params }) as Promise<ExchangeAccountListRes>
  },

  create(data: CreateExchangeAccountDto): Promise<ExchangeAccountListItem> {
    return request.post('/v1/exchange-accounts', data) as Promise<ExchangeAccountListItem>
  },

  update(id: string, data: UpdateExchangeAccountDto): Promise<ExchangeAccountListItem> {
    return request.put(`/v1/exchange-accounts/${id}`, data) as Promise<ExchangeAccountListItem>
  },

  remove(id: string): Promise<void> {
    return request.delete(`/v1/exchange-accounts/${id}`) as Promise<void>
  },

  verify(id: string): Promise<VerifyResult> {
    return request.post(`/v1/exchange-accounts/${id}/verify`) as Promise<VerifyResult>
  },
}

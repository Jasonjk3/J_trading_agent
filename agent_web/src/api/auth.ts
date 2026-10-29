import { request } from './request'
import type { UserInfo } from '@/stores/user'

/** 后端登录响应结构 */
export interface LoginRes {
  access_token: string
  token_type: string
  user: {
    id: string
    username: string
    email?: string
    role: string
    is_active: boolean
    feature_permissions?: string[]
    created_at: string
    updated_at: string
  }
}

/** 转换后端用户数据为前端格式 */
function transformUser(backendUser: LoginRes['user']): UserInfo {
  return {
    id: backendUser.id,
    username: backendUser.username,
    role: backendUser.role,
    email: backendUser.email,
    isActive: backendUser.is_active,
    featurePermissions: backendUser.feature_permissions,
  }
}

export const authApi = {
  async login(username: string, password: string): Promise<{ token: string; user: UserInfo }> {
    const res = await request.post<LoginRes>('/v1/auth/login', { username, password })
    return {
      token: res.access_token,
      user: transformUser(res.user),
    }
  },

  logout(): Promise<void> {
    return request.post('/v1/auth/logout')
  },

  /** 获取当前用户信息 */
  async getCurrentUser(): Promise<UserInfo> {
    const res = await request.get<LoginRes['user']>('/v1/auth/me')
    return transformUser(res)
  },

  /** 重置密码 */
  resetPassword(username: string, oldPassword: string, newPassword: string): Promise<void> {
    return request.post('/v1/auth/reset-password', {
      username,
      old_password: oldPassword,
      new_password: newPassword,
    })
  },
}

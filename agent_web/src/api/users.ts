import { request } from './request'

/** 用户状态 */
export type UserStatus = 'active' | 'disabled'

/** 用户角色 */
export type UserRole = 'admin' | 'user'

/** 后端用户数据结构 */
export interface BackendUser {
  id: string
  username: string
  email?: string
  role: UserRole
  is_active: boolean
  feature_permissions?: string[]
  created_at: string
  updated_at: string
}

/** 前端用户列表项 */
export interface UserListItem {
  id: string
  username: string
  email?: string
  role: UserRole
  status: UserStatus
  featurePermissions?: string[]
  createdAt: string
  updatedAt?: string
}

/** 用户列表查询参数 */
export interface UserListParams {
  username?: string
  role?: UserRole
  status?: UserStatus
  page?: number
  pageSize?: number
}

/** 用户列表响应 */
export interface UserListRes {
  list: UserListItem[]
  total: number
}

/** 新增用户表单 */
export interface CreateUserDto {
  username: string
  password: string
  email?: string
  role: UserRole
  status: UserStatus
}

/** 编辑用户表单（密码可选） */
export interface UpdateUserDto {
  password?: string
  email?: string
  role?: UserRole
  status?: UserStatus
}

/** 后端用户列表响应结构 */
interface BackendUserListRes {
  users: BackendUser[]
  total: number
}

/** 将后端用户转换为前端格式 */
function transformUser(user: BackendUser): UserListItem {
  return {
    id: user.id,
    username: user.username,
    email: user.email,
    role: user.role,
    status: user.is_active ? 'active' : 'disabled',
    featurePermissions: user.feature_permissions,
    createdAt: user.created_at,
    updatedAt: user.updated_at,
  }
}

export const usersApi = {
  async getList(params?: UserListParams): Promise<UserListRes> {
    const backendParams: Record<string, any> = {}
    if (params?.username) backendParams.username = params.username
    if (params?.role) backendParams.role = params.role
    if (params?.status) backendParams.is_active = params.status === 'active'
    if (params?.page && params?.pageSize) {
      backendParams.skip = (params.page - 1) * params.pageSize
      backendParams.limit = params.pageSize
    }

    const res = await request.get<BackendUserListRes>('/v1/users', { params: backendParams })
    return {
      list: res.users.map(transformUser),
      total: res.total,
    }
  },

  async create(data: CreateUserDto): Promise<UserListItem> {
    const backendData = {
      username: data.username,
      password: data.password,
      email: data.email,
      role: data.role,
      is_active: data.status === 'active',
    }
    const res = await request.post<BackendUser>('/v1/users', backendData)
    return transformUser(res)
  },

  async update(id: string, data: UpdateUserDto): Promise<UserListItem> {
    const backendData: Record<string, any> = {}
    if (data.password) backendData.password = data.password
    if (data.email !== undefined) backendData.email = data.email
    if (data.role) backendData.role = data.role
    if (data.status !== undefined) backendData.is_active = data.status === 'active'

    const res = await request.put<BackendUser>(`/v1/users/${id}`, backendData)
    return transformUser(res)
  },

  remove(id: string): Promise<void> {
    return request.delete(`/v1/users/${id}`)
  },

  /** 更新用户功能权限 */
  async updatePermissions(id: string, featurePermissions: string[]): Promise<UserListItem> {
    const res = await request.put<BackendUser>(`/v1/users/${id}/permissions`, {
      feature_permissions: featurePermissions,
    })
    return transformUser(res)
  },
}

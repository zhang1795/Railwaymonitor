// 用户信息
export interface UserInfo {
  passwordChangeRequired?: boolean
  id: number
  username: string
  realName: string
  phone: string
  email: string
  role: number
  status: number
  avatar?: string
  createTime?: string
  updateTime?: string
}

// 用户角色
export enum UserRole {
  USER = 0,
  ADMIN = 1,
}

// 用户状态
export enum UserStatus {
  DISABLED = 0,
  ENABLED = 1,
}

// 用户列表查询参数
export interface UserListParams {
  page: number
  size: number
  username?: string
  realName?: string
  phone?: string
  email?: string
  role?: number
  status?: number
}

// 用户列表响应
export interface UserListResult {
  total: number
  list: UserInfo[]
}

// 添加用户参数
export interface AddUserParams {
  username: string
  password: string
  realName: string
  phone: string
  email: string
  role: number
  status: number
}

// 更新用户参数
export interface UpdateUserParams {
  id: number
  username?: string
  realName?: string
  phone?: string
  email?: string
  role?: number
  status?: number
}

// 修改密码参数
export interface UpdatePasswordParams {
  id: number
  oldPassword: string
  newPassword: string
}

// 登录参数
export interface LoginParams {
  username: string
  password: string
}

// 注册参数
export interface RegisterParams {
  username: string
  password: string
  realName: string
  phone: string
  email: string
}

// 用户查询参数
export interface UserQueryParams {
  current: number
  size: number
  username?: string
  realName?: string
  phone?: string
  email?: string
  role?: number
  status?: number
}

// 用户表单数据
export interface UserForm {
  id?: number
  username?: string
  password?: string
  realName: string
  phone: string
  email: string
  role: number
  status: number
} 
import request from './request'
import type { UserQueryParams, UserForm, UserInfo } from '@/types/user'
import type { PageResult } from '@/types/common'

interface LoginResult {
  userInfo: UserInfo
}

// 登录
export const login = (username: string, password: string) => {
  return request.post<UserInfo>('/user/login', { username, password })
}

// 注册
export const register = (data: {
  username: string
  password: string
  realName: string
  phone: string
  email: string
}) => {
  return request.post('/user/register', data)
}

// 退出登录
export const logout = () => {
  return request.post('/user/logout')
}

// 修改密码
export const updatePassword = (data: {
  id: number
  oldPassword: string
  newPassword: string
}) => {
  return request.post('/user/password', data)
}

// 获取用户列表
export const getUserList = (params: UserQueryParams) => {
  return request.get<PageResult<UserInfo>>('/user/page', { params })
}

// 获取用户详情
export const getUserInfo = (id: number) => {
  return request.get<UserInfo>(`/user/${id}`)
}

// 新增用户
export const addUser = (data: UserForm) => {
  return request.post<void>('/user/register', data)
}

// 修改用户
export const updateUser = (data: UserForm) => {
  return request.put<void>('/user', data)
}

// 删除用户
export const deleteUser = (id: number) => {
  return request.delete<void>(`/user/${id}`)
}

// 重置密码
export const resetPassword = (id: number) => {
  return request.put<{temporaryPassword:string}>(`/user/${id}/reset-password`)
} 
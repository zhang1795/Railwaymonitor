import { defineStore } from 'pinia'
import type { UserInfo } from '@/types/user'
import { login, logout, updatePassword, register } from '@/api/user'

export const useUserStore = defineStore('user', {
  state: () => ({
    // 用户信息
    userInfo: localStorage.getItem('userInfo') ? JSON.parse(localStorage.getItem('userInfo')!) : null,
  }),

  actions: {

    // 设置用户信息
    setUserInfo(userInfo: UserInfo) {
      this.userInfo = userInfo
      localStorage.setItem('userInfo', JSON.stringify(userInfo))
    },

    // 清除用户信息
    clearUserInfo() {
      this.userInfo = null
      localStorage.removeItem('userInfo')
    },

    // 登录
    async login(username: string, password: string) {
      try {
        const userInfo = await login(username, password)
        this.setUserInfo(userInfo)
        return userInfo
      } catch (error) {
        this.clearUserInfo()
        throw error
      }
    },

    // 注册
    async register(data: { username: string; password: string; realName: string; phone: string; email: string }) {
      return register(data)
    },

    // 退出登录
    async logout() {
      try {
        await logout()
      } finally {
        this.clearUserInfo()
      }
    },

    // 修改密码
    async updatePassword(data: { id: number; oldPassword: string; newPassword: string }) {
      await updatePassword(data)
    },
  },
}) 
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', {
  state: () => ({
    // 侧边栏折叠状态
    sidebarCollapse: false,
    // 暗黑模式
    isDark: false,
  }),

  actions: {
    // 切换侧边栏折叠状态
    toggleSidebar() {
      this.sidebarCollapse = !this.sidebarCollapse
      // 保存到本地存储
      localStorage.setItem('sidebarCollapse', String(this.sidebarCollapse))
    },

    // 切换暗黑模式
    toggleDark() {
      this.isDark = !this.isDark
      // 切换 html 的 class
      document.documentElement.classList.toggle('dark', this.isDark)
      // 保存到本地存储
      localStorage.setItem('isDark', String(this.isDark))
    },

    // 初始化应用状态
    initAppState() {
      // 从本地存储获取侧边栏状态
      const sidebarCollapse = localStorage.getItem('sidebarCollapse')
      if (sidebarCollapse !== null) {
        this.sidebarCollapse = sidebarCollapse === 'true'
      }

      // 从本地存储获取暗黑模式状态
      const isDark = localStorage.getItem('isDark')
      if (isDark !== null) {
        this.isDark = isDark === 'true'
        document.documentElement.classList.toggle('dark', this.isDark)
      }
    },
  },
}) 
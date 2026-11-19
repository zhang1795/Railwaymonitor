import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import NProgress from 'nprogress'
import request from '@/api/request'
import { useUserStore } from '@/stores/user'
import 'nprogress/nprogress.css'

// 路由配置
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/',
    name: 'Layout',
    component: () => import('@/components/Layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: '/dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '首页', icon: 'House' },
      },
      /* {
        path: '/shouye',
        name: 'Shouye',
        component: () => import('@/views/shouye/index.vue'),
        meta: { title: '首页', icon: 'House' },
      }, */
      {
        path: '/monitor',
        name: 'Monitor',
        component: () => import('@/views/monitor/index.vue'),
        meta: { title: '实时监控', icon: 'VideoCamera' },
      },
      { path:'/user', name:'Users', component:() => import('@/views/user/index.vue'), meta:{title:'用户管理',icon:'User',admin:true} },
      { path:'/recordings', name:'Recordings', component:()=>import('@/views/recordings/index.vue'), meta:{title:'录像查询',icon:'VideoCamera'} },
      { path:'/risk-templates', name:'RiskTemplates', component:()=>import('@/views/riskTemplates/index.vue'), meta:{title:'告警策略设置',icon:'Setting',admin:true} },
      { path:'/notifications' , name:'Notifications', component:()=>import('@/views/notifications/index.vue'), meta:{title:'通知发送记录',icon:'Bell',admin:true} },
      {
        path: '/camera',
        name: 'Camera',
        component: () => import('@/views/camera/index.vue'),
        meta: { title: '摄像头管理', icon: 'Camera', admin: true },
      },   
      {
        path: '/Abnormal',
        name: 'Abnormal',
        component: () => import('@/views/Abnormal/index.vue'),
        meta: { title: '异常事件', icon: 'Warning' },
      },
          
      {
        path: '/statistics',
        name: 'Statistics',
        component: () => import('@/views/statistics/index.vue'),
        redirect: '/statistics/overview',
        meta: { title: '统计分析', icon: 'DataLine', admin: true },
        children: [
          {
            path: '/statistics/overview',
            name: 'StatisticsOverview',
            component: () => import('@/views/statistics/Overview.vue'),
            meta: { title: '统计概览', icon: 'DataAnalysis' },
          },
          {
            path: '/statistics/Abnormal-event',
            name: 'AbnormalEventStatistics',
            component: () => import('@/views/statistics/AbnormalEvent.vue'),
            meta: { title: '异常事件统计', icon: 'Warning' },
          },
          {
            path: '/statistics/device-status',
            name: 'DeviceStatusStatistics',
            component: () => import('@/views/statistics/DeviceStatus.vue'),
            meta: { title: '设备状态统计', icon: 'Monitor' },
          },

        ],
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '404' },
  },
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
  // 开启进度条
  NProgress.start()

  // 设置标题
  document.title = String(to.meta.title) + ' - ' + import.meta.env.VITE_APP_TITLE

  // 判断是否需要登录权限
  if (to.path !== '/login') {
    let userInfo: string
    try {
      const user = await request.get('/user/current')
      useUserStore().setUserInfo(user)
      userInfo = JSON.stringify(user)
    } catch {
      useUserStore().clearUserInfo()
      next('/login')
      return
    }

    // 判断是否需要管理员权限
    if (to.meta.admin) {
      const user = JSON.parse(userInfo)
      if (user.role !== 1) {
        next('/dashboard')
        return
      }
    }
  }

  next()
})

// 路由后置守卫
router.afterEach(() => {
  // 关闭进度条
  NProgress.done()
})

export default router

<template>
  <div class="dashboard tech-dashboard">
    <!-- 欢迎语容器（垂直+水平居中） -->
    <div class="welcome-container">
      <h1 class="welcome-text">欢迎使用铁路沿线检测系统</h1>
    </div>
  </div>
</template>

<script setup lang="ts">
// 清空所有业务逻辑，仅保留组件基础结构
</script>

<style lang="scss" scoped>
.tech-dashboard {
  padding: 20px;
  background-color: #0a1929; // 保留原有背景色
  background-image: 
    radial-gradient(circle at 25% 25%, rgba(5, 25, 55, 0.7) 0%, transparent 50%),
    radial-gradient(circle at 75% 75%, rgba(5, 25, 55, 0.7) 0%, transparent 50%); // 保留原有渐变背景
  min-height: 100vh;
  color: #e1e1e1;

  // 欢迎语容器：垂直+水平居中
  .welcome-container {
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    height: calc(100vh - 40px); // 减去外层padding，占满剩余高度
  }

  // 欢迎语文本样式（匹配科技感风格）
  .welcome-text {
    font-size: 32px;
    font-weight: 600;
    color: #e1e1e1;
    text-align: center;
    text-shadow: 0 0 20px rgba(0, 144, 255, 0.5); // 科技感发光阴影
    letter-spacing: 2px;
    padding: 20px 40px;
    border-radius: 12px;
    background: rgba(10, 25, 41, 0.6); // 半透明背景板
    border: 1px solid rgba(0, 144, 255, 0.3); // 边框高亮
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
  }
}

// 响应式适配（小屏幕缩小字体）
@media (max-width: 768px) {
  .tech-dashboard {
    padding: 15px;

    .welcome-text {
      font-size: 24px;
      padding: 15px 30px;
    }
  }
}
</style>
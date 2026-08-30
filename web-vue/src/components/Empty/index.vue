<template>
  <div class="empty">
    <el-empty :image-size="200" :description="description">
      <template #image>
        <slot name="image">
          <img src="@/assets/images/empty.png" alt="empty" />
        </slot>
      </template>
      <template #default>
        <slot>
          <el-button type="primary" @click="$emit('create')">
            {{ createText }}
          </el-button>
        </slot>
      </template>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
defineProps({
  description: {
    type: String,
    default: '暂无数据',
  },
  createText: {
    type: String,
    default: '立即创建',
  },
})

defineEmits(['create'])
</script>

<style lang="scss" scoped>
.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
  
  :deep(.el-empty__image) {
    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
  }
}
</style> 
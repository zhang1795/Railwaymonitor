<template>
  <div class="table-toolbar">
    <div class="left">
      <slot name="left">
        <el-button type="primary" @click="$emit('create')">
          <el-icon>
            <Plus />
          </el-icon>
          {{ createText }}
        </el-button>
      </slot>
    </div>
    <div class="right">
      <slot name="right">
        <el-tooltip content="刷新" placement="top">
          <el-icon class="action-icon" :class="{ 'is-loading': loading }" @click="$emit('refresh')">
            <Refresh />
          </el-icon>
        </el-tooltip>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps({
  createText: {
    type: String,
    default: '新建',
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['create', 'refresh'])
</script>

<style lang="scss" scoped>
.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  
  .right {
    display: flex;
    align-items: center;
    
    .action-icon {
      font-size: 20px;
      cursor: pointer;
      margin-left: 10px;
      
      &:hover {
        color: var(--el-color-primary);
      }
      
      &.is-loading {
        animation: rotate 1s linear infinite;
      }
    }
  }
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style> 
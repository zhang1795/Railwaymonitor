<template>
  <div class="pagination">
    <el-pagination
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      :total="total"
      :background="true"
      layout="total, sizes, prev, pager, next, jumper"
      @size-change="handleSizeChange"
      @current-change="handleCurrentChange"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps({
  current: {
    type: Number,
    default: 1,
  },
  size: {
    type: Number,
    default: 10,
  },
  total: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits(['update:current', 'update:size', 'change'])

const currentPage = ref(props.current)
const pageSize = ref(props.size)

// 监听 props 变化
watch(() => props.current, (val) => {
  currentPage.value = val
})

watch(() => props.size, (val) => {
  pageSize.value = val
})

// 处理页码变化
const handleCurrentChange = (val: number) => {
  emit('update:current', val)
  emit('change', { current: val, size: pageSize.value })
}

// 处理每页条数变化
const handleSizeChange = (val: number) => {
  emit('update:size', val)
  emit('change', { current: currentPage.value, size: val })
}
</script>

<style lang="scss" scoped>
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}
</style> 
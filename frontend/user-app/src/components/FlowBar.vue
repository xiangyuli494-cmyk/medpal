<script setup>
import { computed } from 'vue';

/**
 * 进度条：对外 9 步，与 store.publicStep 一致。
 * 协议的 11 节点换算在 constants/status.js 完成，组件不参与换算。
 */
const props = defineProps({
  index: { type: Number, default: 1 },
  total: { type: Number, default: 9 },
  label: { type: String, default: '' },
  done: { type: Boolean, default: false },
  why: { type: String, default: '' },
});

const percent = computed(() => {
  const total = Math.max(props.total, 1);
  const index = Math.min(Math.max(props.index, 1), total);
  return Math.round((index / total) * 100);
});

const caption = computed(() =>
  props.done ? `已完成 · 共 ${props.total} 步` : `第 ${props.index} / ${props.total} 步 · ${props.label}`,
);
</script>

<template>
  <view class="flow">
    <view class="flow__head">
      <text class="flow__caption">{{ caption }}</text>
      <text v-if="why && !done" class="flow__why">{{ why }}</text>
    </view>
    <view class="flow__track">
      <view class="flow__fill" :style="{ width: `${percent}%` }" />
    </view>
  </view>
</template>

<style scoped>
.flow {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.flow__head {
  display: flex;
  flex-direction: row;
  gap: 10px;
  align-items: baseline;
  justify-content: space-between;
}

.flow__caption {
  flex: 1;
  color: var(--mp-gold-strong);
  font-size: var(--font-caption);
  font-weight: 700;
}

.flow__why {
  color: var(--mp-muted);
  font-size: 12px;
}

.flow__track {
  width: 100%;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #eadfcd;
}

.flow__fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #d9ad5b, #b8862f);
  transition: width 0.35s ease;
}
</style>
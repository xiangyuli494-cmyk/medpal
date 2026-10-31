<script setup>
/**
 * 9 步进度列表；state 取 done / current / upcoming，由 constants/status.js 计算。
 */
defineProps({
  steps: { type: Array, default: () => [] },
});
</script>

<template>
  <view class="steps">
    <view
      v-for="step in steps"
      :key="step.key"
      class="steps__item"
      :class="`steps__item--${step.state}`"
    >
      <view class="steps__marker">
        <text class="steps__index">{{ step.index }}</text>
      </view>
      <text class="steps__label">{{ step.label }}</text>
      <text v-if="step.state === 'current'" class="tag tag--wait">当前</text>
      <text v-else-if="step.state === 'done'" class="tag">已完成</text>
    </view>
  </view>
</template>

<style scoped>
.steps {
  display: flex;
  flex-direction: column;
}

.steps__item {
  display: flex;
  flex-direction: row;
  gap: 12px;
  align-items: center;
  min-height: 52px;
  padding: 8px 0;
  border-bottom: 1px solid var(--mp-line);
}

.steps__item:last-child {
  border-bottom: none;
}

.steps__marker {
  display: flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #efe6d6;
}

.steps__index {
  color: var(--mp-muted);
  font-size: 14px;
}

.steps__label {
  flex: 1;
  font-size: var(--font-body);
}

.steps__item--current .steps__marker {
  background: var(--mp-gold);
}

.steps__item--current .steps__index {
  color: #2a1c05;
  font-weight: 700;
}

.steps__item--current .steps__label {
  font-weight: 700;
}

.steps__item--done .steps__marker {
  background: var(--mp-green-soft);
}

.steps__item--done .steps__index {
  color: var(--mp-green);
}

.steps__item--upcoming .steps__label {
  color: var(--mp-muted);
}
</style>
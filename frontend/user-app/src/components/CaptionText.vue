<script setup>
import { computed } from 'vue';
import { splitByEmphasis } from '../utils/highlight.js';

/**
 * 字幕文本：emphasis 子串加粗，不改字。
 * 无障碍：整块给 aria-live，读屏会念新增内容。
 */
const props = defineProps({
  text: { type: String, default: '' },
  emphasis: { type: Array, default: () => [] },
});

const segments = computed(() => splitByEmphasis(props.text, props.emphasis));
</script>

<template>
  <view class="caption" aria-live="polite">
    <text v-if="!segments.length" class="caption__empty">正在准备…</text>
    <text
      v-for="(segment, index) in segments"
      :key="index"
      class="caption__segment"
      :class="{ 'caption__segment--strong': segment.strong }"
    >{{ segment.text }}</text>
  </view>
</template>

<style scoped>
.caption {
  font-size: var(--font-hero);
  font-weight: 500;
  line-height: 1.45;
  word-break: break-word;
}

.caption__segment {
  font-size: var(--font-hero);
}

.caption__segment--strong {
  color: var(--mp-gold-strong);
  font-weight: 700;
}

.caption__empty {
  color: var(--mp-muted);
  font-size: var(--font-body);
}
</style>
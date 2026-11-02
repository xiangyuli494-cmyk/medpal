<script setup>
/**
 * 主操作按钮。
 *
 * 触控区不小于 56px 高（docs/specs/device-ia.md §2.5 的设备端口径是 88px，
 * 手机端按 56px 起步，老人通道靠 .page 的字号档位放大）。
 * 按压反馈用 CSS active，不依赖震动。
 */
defineProps({
  label: { type: String, default: '' },
  tone: { type: String, default: 'primary' },
});

const emit = defineEmits(['tap']);

function onTap() {
  emit('tap');
}
</script>

<template>
  <button
    class="elder-button"
    :class="`elder-button--${tone}`"
    :aria-label="label"
    @tap="onTap"
  >
    <text class="elder-button__text">{{ label }}</text>
  </button>
</template>

<style scoped>
.elder-button {
  display: flex;
  width: 100%;
  min-height: 56px;
  align-items: center;
  justify-content: center;
  padding: 0 20px;
  border-radius: 16px;
  font-size: var(--font-button);
  font-weight: 700;
  line-height: 1.3;
  text-align: center;
}

.elder-button--primary {
  background: linear-gradient(135deg, #d9ad5b 0%, #b8862f 100%);
  color: #2a1c05;
}

.elder-button--ghost {
  border: 1px solid var(--mp-line);
  background: var(--mp-card);
  color: var(--mp-ink);
  font-weight: 500;
}

.elder-button--danger {
  background: var(--mp-red);
  color: #fff;
}

.elder-button:active {
  transform: translateY(1px);
  filter: brightness(0.96);
}

.elder-button__text {
  font-size: var(--font-button);
}
</style>
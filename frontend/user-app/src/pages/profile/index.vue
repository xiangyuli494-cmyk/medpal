<script setup>
import { computed } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import AppHeader from '@/components/AppHeader.vue';
import ElderButton from '@/components/ElderButton.vue';
import { useSessionStore } from '@/stores/session.js';
import { ACCESSIBILITY_MODES, DISCLAIMERS } from '@/constants/copy.js';

const store = useSessionStore();

const scales = [
  { value: 1, label: '标准' },
  { value: 1.15, label: '放大' },
  { value: 1.3, label: '特大' },
];

const modeHint = computed(
  () => ACCESSIBILITY_MODES.find((item) => item.key === store.settings.mode)?.hint || '',
);

onLoad(() => {
  store.hydrate();
});

function pickScale(value) {
  store.setScale(value);
}

function pickMode(key) {
  store.setMode(key);
}

function toggleFamily(event) {
  store.setFamilyVisible(event.detail.value);
  uni.showToast({
    title: event.detail.value ? '家属可见已打开' : '家属可见已关闭',
    icon: 'none',
  });
}

function resetAll() {
  store.resetSettings();
  uni.showToast({ title: '已恢复默认', icon: 'none' });
}
</script>

<template>
  <view class="page" :style="{ '--scale': store.scaleValue }">
    <AppHeader title="我的" subtitle="设置只在本机生效" show-back />

    <view class="card stack">
      <text class="panel-title">字号</text>
      <view class="segmented">
        <button
          v-for="item in scales"
          :key="item.value"
          class="segmented__item"
          :class="{ 'segmented__item--on': store.settings.scale === item.value }"
          @tap="pickScale(item.value)"
        >
          <text>{{ item.label }}</text>
        </button>
      </view>
      <text class="muted">当前倍率 {{ store.settings.scale }}×；老人通道建议不小于「放大」。</text>
    </view>

    <view class="card stack">
      <text class="panel-title">通道</text>
      <view class="modes">
        <button
          v-for="mode in ACCESSIBILITY_MODES"
          :key="mode.key"
          class="mode"
          :class="{ 'mode--on': store.settings.mode === mode.key }"
          @tap="pickMode(mode.key)"
        >
          <text class="mode__label">{{ mode.label }}</text>
          <text class="mode__hint">{{ mode.hint }}</text>
        </button>
      </view>
      <text class="muted">通道选择会随 session.hello 上报服务端：{{ modeHint }}</text>
    </view>

    <view class="card stack">
      <view class="row row--between">
        <view class="list-row__main">
          <text class="panel-title">家属可见</text>
          <text class="muted">关闭后家属端立即看不到时间轴；撤销不做缓存宽限。</text>
        </view>
        <switch
          :checked="store.settings.familyVisible"
          color="#b8862f"
          @change="toggleFamily"
        />
      </view>
      <text class="note">{{ DISCLAIMERS.family }}</text>
    </view>

    <view class="card stack">
      <text class="panel-title">关于</text>
      <text class="reading">小暖陪诊用户端骨架 · 协议 v0.1 · uni-app（Vue 3）</text>
      <text class="muted">主演示形态是 H5；小程序为开发者工具预览，不上架。</text>
      <text class="muted">{{ DISCLAIMERS.triage }}</text>
    </view>

    <ElderButton label="恢复默认设置" tone="ghost" @tap="resetAll" />
  </view>
</template>

<style scoped>
.row--between {
  justify-content: space-between;
}

.segmented {
  display: flex;
  flex-direction: row;
  gap: 8px;
}

.segmented__item {
  flex: 1;
  min-height: 52px;
  border: 1px solid var(--mp-line);
  border-radius: 14px;
  background: var(--mp-card);
  font-size: var(--font-body);
  line-height: 52px;
  text-align: center;
}

.segmented__item--on {
  border-color: var(--mp-gold);
  background: var(--mp-gold-soft);
  color: var(--mp-gold-strong);
  font-weight: 700;
}

.modes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mode {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 2px;
  padding: 14px 16px;
  border: 1px solid var(--mp-line);
  border-radius: 14px;
  background: var(--mp-card);
  text-align: left;
}

.mode--on {
  border-color: var(--mp-gold);
  background: var(--mp-gold-soft);
}

.mode__label {
  font-size: var(--font-body);
  font-weight: 700;
}

.mode__hint {
  color: var(--mp-muted);
  font-size: 13px;
}
</style>
<script setup>
import { computed, ref } from 'vue';

/**
 * 统一页头。
 *
 * 布局：[返回] [标题] [状态]，右侧在微信小程序里再让出胶囊按钮的宽度。
 * 小程序没有系统导航栏（pages.json 里 navigationStyle: custom），
 * 顶部的状态栏与右上角胶囊都要自己让位，否则按钮会和胶囊叠在一起。
 */
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  tone: { type: String, default: 'idle' },
  showBack: { type: Boolean, default: false },
});

/** 小程序胶囊占用的右侧宽度；H5 为 0 */
const capsuleRight = ref(0);
/** 顶栏上沿：至少要越过状态栏，否则返回按钮会被时间/信号盖住 */
const headerTop = ref(8);

// #ifdef MP-WEIXIN
try {
  const info = typeof uni.getWindowInfo === 'function' ? uni.getWindowInfo() : uni.getSystemInfoSync();
  const statusBar = Number(info.statusBarHeight) || 20;
  // 没有胶囊信息时（部分真机/旧基础库），按状态栏高度让位，不能退回 0
  headerTop.value = statusBar + 6;

  const rect = uni.getMenuButtonBoundingClientRect();
  if (rect && rect.left) {
    capsuleRight.value = Math.max(info.windowWidth - rect.left + 8, 0);
    // 胶囊垂直居中：页头上下留白取胶囊上下间距，视觉上对齐
    headerTop.value = Math.max(rect.top, 8);
  }
} catch {
  // 取不到窗口信息时保留默认值，页面仍可用
}
// #endif

const barStyle = computed(() => ({
  paddingTop: `${headerTop.value}px`,
  paddingRight: `${capsuleRight.value + 20}px`,
}));
function goBack() {
  uni.navigateBack({ fail: () => uni.reLaunch({ url: '/pages/home/index' }) });
}
</script>

<template>
  <view class="header" :style="barStyle">
    <view class="header__left">
      <button v-if="showBack" class="header__back" aria-label="返回上一页" @tap="goBack">
        <text class="header__back-text">返回</text>
      </button>
      <view v-else class="header__status">
        <view class="header__dot" :class="`header__dot--${tone}`" />
        <text class="header__status-text">{{ subtitle }}</text>
      </view>
    </view>

    <text class="header__title">{{ title }}</text>

    <view class="header__right">
      <template v-if="showBack">
        <view class="header__dot" :class="`header__dot--${tone}`" />
        <text class="header__status-text">{{ subtitle }}</text>
      </template>
    </view>
  </view>
</template>

<style scoped>
.header {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding-bottom: 10px;
  padding-left: 20px;
}

.header__left {
  display: flex;
  min-width: 76px;
  flex-direction: row;
  align-items: center;
  gap: 6px;
}

.header__right {
  display: flex;
  min-width: 76px;
  flex-direction: row;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.header__status {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
}

.header__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #b3a894;
}

.header__dot--open,
.header__dot--ready,
.header__dot--mock {
  background: var(--mp-green);
}

.header__dot--connecting,
.header__dot--reconnecting {
  background: var(--mp-gold);
}

.header__dot--error,
.header__dot--closed {
  background: var(--mp-red);
}

.header__status-text {
  color: var(--mp-muted);
  font-size: 13px;
  white-space: nowrap;
}

.header__title {
  flex: 1;
  overflow: hidden;
  font-size: var(--font-title);
  font-weight: 700;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header__back {
  min-width: 64px;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--mp-line);
  border-radius: 999px;
  background: var(--mp-card);
  line-height: 44px;
  text-align: center;
}

.header__back-text {
  color: var(--mp-muted);
  font-size: 15px;
}
</style>
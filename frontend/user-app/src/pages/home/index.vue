<script setup>
import { ref } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import AppHeader from '@/components/AppHeader.vue';
import ElderButton from '@/components/ElderButton.vue';
import { useSessionStore } from '@/stores/session.js';
import { DEFAULT_EPISODE_ID, DEMO_MODE } from '@/config.js';
import { DISCLAIMERS } from '@/constants/copy.js';

const store = useSessionStore();
const episodeId = ref(DEFAULT_EPISODE_ID);

onLoad((query) => {
  store.hydrate();
  if (query?.episode) episodeId.value = query.episode;
  if (query?.autostart === '1') start();
});

function start() {
  const target = String(episodeId.value || '').trim();
  if (!target) {
    uni.showToast({ title: '请填写陪诊单号', icon: 'none' });
    return;
  }
  store.start(target);
  uni.navigateTo({ url: `/pages/session/index?episode=${encodeURIComponent(target)}` });
}

function openJourney() {
  uni.navigateTo({ url: '/pages/journey/index' });
}

function openProfile() {
  uni.navigateTo({ url: '/pages/profile/index' });
}
</script>

<template>
  <view class="page" :class="store.scaleClass">
    <AppHeader title="小暖陪诊" :subtitle="DEMO_MODE ? '演示模式' : '在线'" :tone="DEMO_MODE ? 'mock' : 'idle'" />

    <view class="hero">
      <text class="hero__kicker">院内陪诊 · 用户端</text>
      <text class="hero__title">陪您把今天这一趟，走明白</text>
      <text class="hero__sub">看进度、看医嘱、随时求助。设备端在服务台，手机上是它的远程延伸。</text>
    </view>

    <view class="card stack">
      <text class="label">陪诊单号</text>
      <input
        v-model="episodeId"
        class="field"
        type="text"
        placeholder="例如 ep_001"
        confirm-type="done"
        @confirm="start"
      />
      <ElderButton label="开始陪诊" tone="primary" @tap="start" />
      <text class="muted">演示单号 ep_001；正式使用时由服务台在借出设备时给出。</text>
    </view>

    <view class="shortcuts">
      <button class="shortcut" @tap="openJourney">
        <text class="shortcut__title">陪诊进度</text>
        <text class="shortcut__sub">9 步走到哪了</text>
      </button>
      <button class="shortcut" @tap="openProfile">
        <text class="shortcut__title">无障碍设置</text>
        <text class="shortcut__sub">字号 · 通道 · 家属可见</text>
      </button>
    </view>

    <view v-if="DEMO_MODE" class="note">{{ DISCLAIMERS.demo }}</view>
  </view>
</template>

<style scoped>
.shortcuts {
  display: flex;
  flex-direction: row;
  gap: 12px;
}

.shortcut {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  padding: 18px 16px;
  border: 1px solid var(--mp-line);
  border-radius: var(--mp-radius);
  background: var(--mp-card);
  text-align: left;
}

.shortcut__title {
  font-size: var(--font-body);
  font-weight: 700;
}

.shortcut__sub {
  color: var(--mp-muted);
  font-size: 13px;
}
</style>
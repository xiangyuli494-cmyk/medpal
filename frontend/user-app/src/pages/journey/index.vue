<script setup>
import { computed, ref } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import AppHeader from '@/components/AppHeader.vue';
import FlowBar from '@/components/FlowBar.vue';
import StepList from '@/components/StepList.vue';
import { useSessionStore } from '@/stores/session.js';
import { CONNECTION_LABELS, DISCLAIMERS } from '@/constants/copy.js';
import { createDemoEpisode } from '@/mock/demo-episode.js';
import { fetchEpisode } from '@/api/episodes.js';
import { DEMO_MODE } from '@/config.js';
import { formatIsoShort } from '@/utils/time.js';

const store = useSessionStore();

/** 演示模式直接用本地样例；连真实服务时走 api/ 层，失败回退到样例并提示 */
const episode = ref(createDemoEpisode(store.episodeId || 'ep_001'));

const connectionText = computed(() => CONNECTION_LABELS[store.connection] || store.connection);
const pendingTasks = computed(() => episode.value.tasks.filter((task) => task.status !== 'done'));

async function loadEpisode(episodeId) {
  if (DEMO_MODE || !episodeId) return;
  try {
    const remote = await fetchEpisode(episodeId);
    if (remote && Array.isArray(remote.tasks)) {
      episode.value = {
        ...episode.value,
        ...remote,
        patient: remote.patient || episode.value.patient,
        timeline: remote.timeline || [],
      };
    }
  } catch (error) {
    uni.showToast({ title: error?.message || '陪诊单读取失败', icon: 'none' });
  }
}

onLoad((query) => {
  store.hydrate();
  const target = query?.episode || store.episodeId;
  if (target) {
    store.ensureStarted(target);
    loadEpisode(target);
  }
});

function backToSession() {
  uni.navigateTo({ url: `/pages/session/index?episode=${encodeURIComponent(store.episodeId)}` });
}
</script>

<template>
  <view class="page" :style="{ '--scale': store.scaleValue }">
    <AppHeader
      title="陪诊进度"
      :subtitle="connectionText"
      :tone="store.connection"
      show-back
    />

    <view class="card stack">
      <text class="panel-title">今天走到哪了</text>
      <FlowBar
        :index="store.publicStep.index"
        :total="store.publicStep.total"
        :label="store.publicStep.label"
        :done="store.publicStep.done"
        :why="store.flow.why"
      />
      <button class="link" @tap="backToSession">回到问小暖</button>
    </view>

    <view class="card">
      <text class="panel-title">9 步进度</text>
      <StepList :steps="store.steps" />
    </view>

    <view class="card">
      <text class="panel-title">时间轴</text>
      <view v-if="!store.timeline.length" class="muted">还没有记录。</view>
      <view v-for="(item, index) in store.timeline" :key="index" class="timeline-row">
        <text class="timeline-row__at">{{ item.at }}</text>
        <text class="timeline-row__text">{{ item.text }}</text>
      </view>
    </view>

    <view class="card">
      <text class="panel-title">待办</text>
      <view v-for="task in pendingTasks" :key="task.id" class="list-row">
        <view class="list-row__main">
          <text>{{ task.title }}</text>
          <text class="muted">{{ task.type }}</text>
        </view>
        <text class="tag tag--wait">{{ task.status }}</text>
      </view>
      <view v-if="!pendingTasks.length" class="muted">今天的检查都完成了。</view>
    </view>

    <view class="card">
      <text class="panel-title">陪诊单</text>
      <view class="kv">
        <text class="kv__key">单号</text>
        <text class="kv__value">{{ episode.id }}</text>
      </view>
      <view class="kv">
        <text class="kv__key">称呼</text>
        <text class="kv__value">{{ episode.patient.salutation }}</text>
      </view>
      <view class="kv">
        <text class="kv__key">年龄段</text>
        <text class="kv__value">{{ episode.patient.age_range }}</text>
      </view>
      <view class="kv">
        <text class="kv__key">院内对接人</text>
        <text class="kv__value">{{ episode.staff_contact || '自助完成' }}</text>
      </view>
      <view class="kv">
        <text class="kv__key">最近记录</text>
        <text class="kv__value">{{ formatIsoShort(episode.timeline[0]?.at) }}</text>
      </view>
      <text class="muted">本系统不显示证件号；需要核对身份时找服务台。</text>
    </view>

    <view class="note">{{ DISCLAIMERS.family }}</view>
  </view>
</template>

<style scoped>
.link {
  align-self: flex-start;
  min-height: 44px;
  color: var(--mp-gold-strong);
  font-size: var(--font-caption);
  line-height: 44px;
  text-decoration: underline;
}

.timeline-row {
  display: flex;
  flex-direction: row;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--mp-line);
}

.timeline-row:last-child {
  border-bottom: none;
}

.timeline-row__at {
  width: 72px;
  color: var(--mp-muted);
  font-size: 13px;
}

.timeline-row__text {
  flex: 1;
  font-size: var(--font-caption);
}

.kv {
  display: flex;
  flex-direction: row;
  gap: 12px;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--mp-line);
}

.kv:last-of-type {
  border-bottom: none;
}

.kv__key {
  color: var(--mp-muted);
  font-size: var(--font-caption);
}

.kv__value {
  font-size: var(--font-caption);
  font-weight: 700;
  text-align: right;
}
</style>
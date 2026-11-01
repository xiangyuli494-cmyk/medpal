<script setup>
import { computed, ref } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import AppHeader from '@/components/AppHeader.vue';
import CaptionText from '@/components/CaptionText.vue';
import ElderButton from '@/components/ElderButton.vue';
import FlowBar from '@/components/FlowBar.vue';
import { useSessionStore } from '@/stores/session.js';
import { DEMO_MODE } from '@/config.js';
import { CONNECTION_LABELS, DISCLAIMERS, ESCALATION_COPY } from '@/constants/copy.js';

const store = useSessionStore();
const draft = ref('');

const escalationText = computed(() => ESCALATION_COPY[store.escalation] || '');
const connectionText = computed(() => CONNECTION_LABELS[store.connection] || store.connection);
const hasPrimary = computed(() => Boolean(store.primaryLabel));

onLoad((query) => {
  store.hydrate();
  const episode = query?.episode || store.episodeId;
  if (!episode) {
    uni.showToast({ title: '请先选择陪诊单', icon: 'none' });
    uni.reLaunch({ url: '/pages/home/index' });
    return;
  }
  // 离开页面不主动断开：进度页要继续用同一条连接
  store.ensureStarted(episode);
});

function tapPrimary() {
  if (!hasPrimary.value) return;
  store.sendControl('primary', 'tap');
}

function tapOption(option) {
  store.sendControl(`option:${option.id}`, 'tap');
}

function tapSos() {
  store.sendControl('sos', 'tap');
}

function sendDraft() {
  if (store.sendText(draft.value)) draft.value = '';
}
</script>

<template>
  <view class="page" :style="{ '--scale': store.scaleValue }">
    <AppHeader
      title="问小暖"
      :subtitle="connectionText"
      :tone="store.connection"
      show-back
    />

    <view class="card stack">
      <FlowBar
        :index="store.publicStep.index"
        :total="store.publicStep.total"
        :label="store.publicStep.label"
        :done="store.publicStep.done"
        :why="store.flow.why"
      />
      <CaptionText :text="store.caption.text" :emphasis="store.caption.emphasis" />
    </view>

    <view v-if="escalationText" class="note" :class="{ 'note--danger': store.escalation === 'sos' }">
      {{ escalationText }}
    </view>

    <view v-if="store.errorInfo" class="note note--danger">
      {{ store.errorInfo.message }}
    </view>

    <view v-if="store.options.length" class="pills">
      <button
        v-for="option in store.options"
        :key="option.id"
        class="pill"
        :aria-label="option.label"
        @tap="tapOption(option)"
      >
        <text>{{ option.label }}</text>
      </button>
    </view>

    <ElderButton v-if="hasPrimary" :label="store.primaryLabel" tone="primary" @tap="tapPrimary" />

    <view class="card stack">
      <text class="panel-title">说给小暖听</text>
      <view class="row">
        <input
          v-model="draft"
          class="field field--inline"
          type="text"
          placeholder="文字代替语音（麦克风选型前）"
          confirm-type="send"
          @confirm="sendDraft"
        />
        <button class="send" aria-label="发送文字" @tap="sendDraft">
          <text>发送</text>
        </button>
      </view>
      <ElderButton label="一键求助" tone="danger" @tap="tapSos" />
      <text class="muted">求助会同时通知服务台与家属；不需要长按，点一下就行。</text>
    </view>

    <view class="card stack">
      <view class="row">
        <text class="panel-title">数据流</text>
        <text class="muted">本轮共 {{ store.turn }} 轮</text>
      </view>
      <view v-if="!store.dataflow.length" class="muted">等待第一轮交互…</view>
      <view v-for="(item, index) in store.dataflow" :key="index" class="flow-row">
        <text class="flow-row__dir">{{ item.dir }}</text>
        <text class="flow-row__type">{{ item.type }}</text>
        <text class="flow-row__at">{{ item.at }}</text>
      </view>
    </view>

    <view v-if="DEMO_MODE" class="note">{{ DISCLAIMERS.demo }}</view>
  </view>
</template>

<style scoped>
.send {
  min-width: 76px;
  min-height: 56px;
  padding: 0 18px;
  border-radius: 14px;
  background: var(--mp-gold-soft);
  color: var(--mp-gold-strong);
  font-size: var(--font-body);
  font-weight: 700;
  line-height: 56px;
}

.flow-row {
  display: flex;
  flex-direction: row;
  gap: 10px;
  align-items: center;
  font-size: 13px;
}

.flow-row__dir {
  width: 18px;
  color: var(--mp-gold-strong);
  font-weight: 700;
}

.flow-row__type {
  flex: 1;
  color: var(--mp-ink);
}

.flow-row__at {
  color: var(--mp-muted);
}
</style>
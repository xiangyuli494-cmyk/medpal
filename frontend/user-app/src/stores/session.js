/**
 * 会话状态（pinia）。
 *
 * 权威状态在服务端（docs/api/ws-protocol.md §1）：客户端只根据下行消息渲染，
 * 不自行推进节点。本 store 只保存「服务端最近一次下发的东西」与本地渲染设置。
 */

import { defineStore } from 'pinia';
import { DEFAULT_ACCESSIBILITY_MODE, DEFAULT_EPISODE_ID, LOG_LIMIT, TIMELINE_LIMIT } from '../config.js';
import { createTransport } from '../services/transport.js';
import {
  buildAck,
  buildHello,
  buildTextInput,
  buildTouch,
  classifyMessage,
  normalizeTurnResult,
  parseMessage,
} from '../services/protocol.js';
import { buildStepList, statusLabel, toPublicStep } from '../constants/status.js';
import { loadSettings, saveSettings } from '../utils/storage.js';
import { formatTime } from '../utils/time.js';

const DEFAULT_SETTINGS = {
  scale: 1,
  mode: DEFAULT_ACCESSIBILITY_MODE,
  familyVisible: true,
};

/** 非响应式的传输实例：换连接时整体替换，不参与渲染 */
let transport = null;

export const useSessionStore = defineStore('session', {
  state: () => ({
    settings: { ...DEFAULT_SETTINGS },
    hydrated: false,

    episodeId: '',
    sessionId: '',
    connection: 'idle',
    lastPongAt: 0,

    turn: 0,
    caption: { text: '', emphasis: [] },
    primaryLabel: '',
    options: [],
    escalation: 'none',
    flow: { step: '', stepIndex: 0, total: 11, why: '' },
    publicStep: { index: 1, total: 9, label: '', done: false },
    steps: buildStepList(1),
    timeline: [],
    dataflow: [],
    errorInfo: null,
  }),

  getters: {
    scaleValue: (state) => state.settings.scale,
  },

  actions: {
    hydrate() {
      if (this.hydrated) return;
      const saved = loadSettings();
      if (saved) {
        this.settings = {
          ...DEFAULT_SETTINGS,
          ...saved,
          scale: Number(saved.scale) || DEFAULT_SETTINGS.scale,
        };
      }
      this.hydrated = true;
    },

    setScale(value) {
      this.settings.scale = Number(value) || 1;
      this.persist();
    },

    setMode(value) {
      this.settings.mode = value || DEFAULT_ACCESSIBILITY_MODE;
      this.persist();
    },

    setFamilyVisible(value) {
      this.settings.familyVisible = Boolean(value);
      this.persist();
    },

    resetSettings() {
      this.settings = { ...DEFAULT_SETTINGS };
      this.persist();
    },

    persist() {
      saveSettings({
        scale: this.settings.scale,
        mode: this.settings.mode,
        familyVisible: this.settings.familyVisible,
      });
    },

    /** 已连到同一个陪诊单就不重连 */
    ensureStarted(episodeId) {
      this.hydrate();
      const target = episodeId || this.episodeId || DEFAULT_EPISODE_ID;
      if (transport && this.episodeId === target && this.connection !== 'idle') return;
      this.start(target);
    },

    start(episodeId) {
      this.stop();
      this.episodeId = episodeId || DEFAULT_EPISODE_ID;
      this.sessionId = '';
      this.turn = 0;
      this.caption = { text: '', emphasis: [] };
      this.primaryLabel = '';
      this.options = [];
      this.escalation = 'none';
      this.flow = { step: '', stepIndex: 0, total: 11, why: '' };
      this.publicStep = { index: 1, total: 9, label: '', done: false };
      this.steps = buildStepList(1);
      this.timeline = [];
      this.dataflow = [];
      this.errorInfo = null;

      transport = createTransport({
        episodeId: this.episodeId,
        onMessage: (raw) => this.ingest(raw),
        onState: (state) => {
          this.connection = state;
          this.pushDataflow('·', `连接状态 ${state}`);
        },
        onOpen: () => this.sendHello(),
      });
      transport.connect();
    },

    stop() {
      if (transport) {
        transport.close();
        transport = null;
      }
      this.connection = 'idle';
    },

    sendHello() {
      this.transportSend(
        buildHello({
          episodeId: this.episodeId,
          deviceId: 'user_app',
          accessibilityMode: this.settings.mode,
        }),
      );
    },

    /** 屏内控件与选项统一走这里 */
    sendControl(target, action = 'tap') {
      if (!target) return;
      const payload = buildTouch({ sessionId: this.sessionId, target, action });
      this.transportSend(payload);
    },

    sendText(text) {
      if (!String(text || '').trim()) return false;
      const payload = buildTextInput({ sessionId: this.sessionId, text });
      this.transportSend(payload);
      return true;
    },

    transportSend(payload) {
      if (!payload) return;
      if (!transport) {
        this.pushDataflow('!', `未连接，未发送 ${payload.type}`);
        return;
      }
      this.pushDataflow('↑', payload.type);
      transport.send(payload);
    },

    /**
     * 下行消息入口：原始字符串 → 解析 → 分类 → 更新状态。
     * 无法识别的消息只记日志，不改界面（不得因为一条坏消息打断老人）。
     */
    ingest(raw) {
      const message = parseMessage(raw);
      if (!message) {
        this.pushDataflow('!', '收到无法解析的下行消息');
        return;
      }

      this.pushDataflow('↓', message.type || 'unknown');

      switch (classifyMessage(message)) {
        case 'ready':
          this.sessionId = message.session_id || this.sessionId;
          this.connection = 'ready';
          if (message.state) {
            this.applyStep(message.state);
          }
          this.pushTimeline(`已连接陪诊单 ${this.episodeId}`);
          break;

        case 'turn':
          this.applyTurn(message);
          break;

        case 'reply':
          if (typeof message.text === 'string') {
            this.caption = { text: message.text, emphasis: [] };
          }
          if (typeof message.primary_label === 'string') {
            this.primaryLabel = message.primary_label;
          }
          break;

        case 'transition':
          if (message.to) {
            this.applyStep(message.to);
            this.pushTimeline(`进入「${statusLabel(message.to)}」`);
          }
          break;

        case 'escalation':
          this.escalation = message.target ? 'call_staff' : this.escalation;
          if (message.reason) this.pushTimeline(`升级：${message.reason}`);
          break;

        case 'error':
          this.errorInfo = {
            code: message.code || '',
            message: message.message || '连接有点问题，正在重试',
          };
          this.pushDataflow('!', `${message.code || 'error'}`);
          break;

        case 'pong':
          this.lastPongAt = Date.now();
          break;

        default:
          break;
      }
    },

    applyTurn(message) {
      const turn = normalizeTurnResult(message);
      if (!turn) {
        this.pushDataflow('!', 'turn_result 字段不完整，已忽略');
        return;
      }

      const previousStep = this.flow.step;
      this.turn = turn.turn;
      this.sessionId = turn.session || this.sessionId;
      this.caption = turn.caption;
      this.primaryLabel = turn.primaryLabel;
      this.options = turn.options;
      this.escalation = turn.escalation;
      this.flow = turn.flow;
      this.publicStep = turn.publicStep;
      this.steps = buildStepList(turn.publicStep.index, turn.publicStep.done);
      this.errorInfo = null;

      if (turn.flow.step !== previousStep) {
        this.pushTimeline(
          `进入「${statusLabel(turn.flow.step)}」${turn.flow.why ? ` · ${turn.flow.why}` : ''}`,
        );
      }

      // 送达确认：服务端据此决定重连后从哪一轮补发（协议 §7.1）
      this.transportSend(buildAck({ sessionId: this.sessionId, turn: turn.turn }));
    },

    applyStep(step) {
      const publicStep = toPublicStep({ step });
      this.flow = {
        ...this.flow,
        step,
        stepIndex: publicStep.index,
        why: this.flow.why,
      };
      this.publicStep = publicStep;
      this.steps = buildStepList(publicStep.index, publicStep.done);
    },

    pushTimeline(text) {
      this.timeline = [
        { at: formatTime(), text },
        ...this.timeline,
      ].slice(0, TIMELINE_LIMIT);
    },

    pushDataflow(dir, type) {
      this.dataflow = [
        { at: formatTime(), dir, type },
        ...this.dataflow,
      ].slice(0, LOG_LIMIT);
    },
  },
});
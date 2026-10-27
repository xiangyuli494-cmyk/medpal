/**
 * 会话协议 v0.1 的构造与解析（纯函数，可单测）。
 *
 * wire 格式唯一来源：docs/api/ws-protocol.md。
 * 本文件只做形状校验与字段归一，不含业务判断。
 */

import {
  PROTOCOL_VERSION,
  CLIENT_KIND,
} from '../config.js';
import { STATUS_ORDER, toPublicStep } from '../constants/status.js';
import { ESCALATION_LEVELS } from '../constants/copy.js';

const ESCALATION_SET = new Set(ESCALATION_LEVELS);
const STATUS_SET = new Set(STATUS_ORDER);

/** 上行：会话初始化 */
export function buildHello({ episodeId, deviceId, accessibilityMode = 'elder' }) {
  if (!episodeId) throw new Error('缺少 episodeId');
  return {
    type: 'session.hello',
    protocol_version: PROTOCOL_VERSION,
    device_id: deviceId || 'user_app',
    episode_id: episodeId,
    client: CLIENT_KIND,
    accessibility_mode: accessibilityMode,
  };
}

/** 上行：触摸事件 */
export function buildTouch({ sessionId, target, action = 'tap' }) {
  if (!target) throw new Error('缺少 target');
  return { type: 'touch.event', session: sessionId, target, action };
}

/** 上行：文字输入 */
export function buildTextInput({ sessionId, text }) {
  const value = String(text || '').trim();
  if (!value) throw new Error('文字为空');
  return { type: 'text.input', session: sessionId, text: value };
}

/** 上行：轮次回执 */
export function buildAck({ sessionId, turn }) {
  return { type: 'ack', session: sessionId, turn };
}

/** 上行：保活 */
export function buildPing() {
  return { type: 'ping' };
}

/**
 * 把 onMessage 收到的原始数据解析成对象。
 * 小程序与 H5 都可能给字符串；二进制帧（TTS 音频）本骨架不处理，返回 null。
 */
export function parseMessage(raw) {
  if (typeof raw !== 'string') return null;
  try {
    const data = JSON.parse(raw);
    return data && typeof data === 'object' ? data : null;
  } catch {
    return null;
  }
}

function toInt(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.trunc(number) : null;
}

/**
 * 校验并归一 turn_result。
 * 缺少 caption / flow / turn 的消息视为无效，返回 null，由调用方记日志。
 */
export function normalizeTurnResult(raw) {
  if (!raw || raw.type !== 'turn_result') return null;

  const turn = toInt(raw.turn);
  if (turn === null || turn < 0) return null;

  const caption = raw.caption && typeof raw.caption.text === 'string' ? raw.caption : null;
  const flow = raw.flow && STATUS_SET.has(raw.flow.step) ? raw.flow : null;
  if (!caption || !flow) return null;

  const stepIndex = toInt(flow.step_index);
  const total = toInt(flow.total);
  const escalation = ESCALATION_SET.has(raw.escalation?.level)
    ? raw.escalation.level
    : 'none';

  return {
    type: 'turn_result',
    session: typeof raw.session === 'string' ? raw.session : '',
    turn,
    caption: {
      text: caption.text,
      emphasis: Array.isArray(caption.emphasis) ? caption.emphasis.filter(isText) : [],
    },
    speech: {
      audioUrl: typeof raw.speech?.audio_url === 'string' ? raw.speech.audio_url : '',
      rate: Number(raw.speech?.rate) || 0.86,
      canInterrupt: raw.speech?.can_interrupt !== false,
    },
    flow: {
      step: flow.step,
      stepIndex: stepIndex === null ? STATUS_ORDER.indexOf(flow.step) + 1 : stepIndex,
      total: total === null ? STATUS_ORDER.length : total,
      why: typeof flow.why === 'string' ? flow.why : '',
    },
    escalation,
    primaryLabel: typeof raw.primary_label === 'string' ? raw.primary_label : '',
    options: normalizeOptions(raw.options),
    publicStep: toPublicStep(flow),
  };
}

function isText(value) {
  return typeof value === 'string' && value.length > 0;
}

function normalizeOptions(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item) => item && isText(item.id) && isText(item.label))
    .slice(0, 5)
    .map((item) => ({ id: item.id, label: item.label }));
}

/**
 * 把下行消息归类，页面只关心这几种。
 * @returns {'ready'|'turn'|'reply'|'transition'|'escalation'|'error'|'pong'|'unknown'}
 */
export function classifyMessage(raw) {
  switch (raw?.type) {
    case 'session.ready':
      return 'ready';
    case 'turn_result':
      return 'turn';
    case 'dialog.reply':
    case 'caption.update':
      return 'reply';
    case 'state.transition':
      return 'transition';
    case 'escalation.notice':
      return 'escalation';
    case 'error':
      return 'error';
    case 'pong':
      return 'pong';
    default:
      return 'unknown';
  }
}
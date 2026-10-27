/**
 * 会话传输层。
 *
 * 两种模式：
 *   mock   —— VITE_DEMO_MODE=1，本地脚本会话，零网络
 *   socket —— uni.connectSocket 连 /ws/session/{episode_id}
 *
 * 传输层只负责收发与重连，不解释消息；消息形状由 services/protocol.js 管。
 */

import { DEMO_MODE, WS_BASE } from '../config.js';
import { createDemoSession } from '../mock/session.js';
import { buildPing } from './protocol.js';

const HEARTBEAT_MS = 15000;
const MAX_RETRY = 5;
const MAX_QUEUE = 20;

/**
 * @param {{
 *   episodeId: string,
 *   onMessage: (raw: string) => void,
 *   onState: (state: string) => void,
 *   onOpen?: () => void,
 * }} options
 */
export function createTransport(options) {
  if (DEMO_MODE) return createMockTransport(options);
  return createSocketTransport(options);
}

function createMockTransport({ onMessage, onState, onOpen }) {
  // 传输层的出口契约是「原始字符串帧」，与 uni.connectSocket 的 onMessage 一致；
  // 演示会话产出的是对象，这里统一序列化，避免 store 收到两种类型。
  const session = createDemoSession({
    onMessage: (payload) => onMessage(JSON.stringify(payload)),
  });

  return {
    mode: 'mock',
    connect() {
      onState('mock');
      onOpen?.();
    },
    send(payload) {
      session.send(payload);
    },
    close() {
      session.close();
      onState('idle');
    },
  };
}

function createSocketTransport({ episodeId, onMessage, onState, onOpen }) {
  const url = `${WS_BASE}/ws/session/${encodeURIComponent(episodeId)}`;

  let task = null;
  let opened = false;
  let closedByUser = false;
  let attempts = 0;
  let retryTimer = 0;
  let heartbeatTimer = 0;
  let queue = [];

  function sendNow(payload) {
    if (!task) return false;
    try {
      task.send({
        data: JSON.stringify(payload),
        fail() {
          // 发送失败由重连兜底；这里不弹提示，避免打断用户
        },
      });
      return true;
    } catch {
      return false;
    }
  }

  function send(payload) {
    if (!opened) {
      queue.push(payload);
      if (queue.length > MAX_QUEUE) queue.shift();
      return false;
    }
    return sendNow(payload);
  }

  function flush() {
    const pending = queue;
    queue = [];
    pending.forEach(sendNow);
  }

  function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = setInterval(() => send(buildPing()), HEARTBEAT_MS);
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = 0;
    }
  }

  function scheduleReconnect() {
    if (closedByUser || retryTimer) return;
    attempts += 1;
    if (attempts > MAX_RETRY) {
      onState('closed');
      return;
    }
    const delay = Math.min(1000 * 2 ** (attempts - 1), 15000);
    onState('reconnecting');
    retryTimer = setTimeout(() => {
      retryTimer = 0;
      open();
    }, delay);
  }

  function open() {
    if (closedByUser) return;
    onState(attempts > 0 ? 'reconnecting' : 'connecting');
    task = uni.connectSocket({ url, complete() {} });
    if (!task || typeof task.onOpen !== 'function') {
      onState('error');
      scheduleReconnect();
      return;
    }

    task.onOpen(() => {
      opened = true;
      attempts = 0;
      onState('open');
      startHeartbeat();
      flush();
      onOpen?.();
    });

    task.onMessage((event) => onMessage(event?.data));

    task.onClose(() => {
      opened = false;
      task = null;
      stopHeartbeat();
      if (closedByUser) onState('idle');
      else scheduleReconnect();
    });

    task.onError(() => {
      opened = false;
      stopHeartbeat();
      onState('error');
      scheduleReconnect();
    });
  }

  return {
    mode: 'socket',
    connect() {
      closedByUser = false;
      open();
    },
    send,
    close() {
      closedByUser = true;
      opened = false;
      stopHeartbeat();
      queue = [];
      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = 0;
      }
      if (task) {
        task.close({ code: 1000, reason: 'user close' });
        task = null;
      }
      onState('idle');
    },
  };
}
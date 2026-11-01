/**
 * mock 会话：在没有后端的情况下走完 11 个节点。
 *
 * 只实现 docs/api/ws-protocol.md 的最小闭环，消息形状与 tools/mock_ws.py 一致：
 *   session.hello → session.ready
 *   touch.event / text.input → turn_result
 *   ping → pong
 *
 * 这是演示脚本，不是业务实现：真实状态机与话术由服务端负责（ADR-003）。
 */

import { STATUS_ORDER } from '../constants/status.js';

const SCRIPT = [
  {
    step: 'ARRIVED',
    caption: '您好，我是小暖。今天由我陪着您，先确认一下，您是王阿姨吗？',
    emphasis: ['小暖', '王阿姨'],
    primary: '是我',
    why: '先核对身份，再开始今天的陪诊',
  },
  {
    step: 'BRIEFING',
    caption: '今天一共三件事：先看医生，再抽血，最后做 B 超。抽血要空腹，所以先抽血再吃东西。',
    emphasis: ['先看医生', '抽血', 'B 超'],
    primary: '我听明白了',
    why: '先讲清一天的安排',
  },
  {
    step: 'REGISTER',
    caption: '请说一下哪里不舒服，也可以点下面的例子。分诊仅作就诊参考，不能替代医生诊断。',
    emphasis: ['哪里不舒服'],
    primary: '去挂号',
    options: [
      { id: 'symptom-leg', label: '腿疼' },
      { id: 'symptom-dizzy', label: '头晕' },
      { id: 'symptom-chest', label: '胸口不舒服' },
    ],
    why: '先听主诉，再挂号',
  },
  {
    step: 'WAITING',
    caption: '您的号码是第 12 位，当前叫到第 8 位，预计等 15 分钟。我帮您盯着号。',
    emphasis: ['第 12 位', '15 分钟'],
    primary: '我去洗手间',
    why: '候诊期间帮您盯号',
  },
  {
    step: 'IN_ROOM',
    caption: '医生正在给您看诊，我在门外等您。出来以后点「我出来了」。',
    emphasis: ['我出来了'],
    primary: '我出来了',
    why: '诊室内不外放，安静等候',
  },
  {
    step: 'RECAP',
    caption: '医生说：抽血查血常规，今天先别吃早饭。您听听对不对。',
    emphasis: ['抽血查血常规', '先别吃早饭'],
    primary: '对，记住了',
    why: '医生原话，逐字复述',
  },
  {
    step: 'PLAN_EXAMS',
    caption: '检查排好了：先抽血，再做 B 超。这样走的路少一些。',
    emphasis: ['先抽血', '再做 B 超'],
    primary: '就这么走',
    why: '空腹项目排在前面',
  },
  {
    step: 'NAVIGATE',
    caption: '2 楼检验科，出电梯往左。',
    emphasis: ['2 楼', '往左'],
    primary: '我到了',
    why: '抽血要空腹',
  },
  {
    step: 'PAY_AND_PICKUP',
    caption: '本次费用总共 128 元，医保出 96 元，自己掏 32 元。最终以医院结算单为准。',
    emphasis: ['128 元', '32 元'],
    primary: '去取药',
    why: '缴费与取药在同一层',
  },
  {
    step: 'REPORT',
    caption: '报告出来了，医生原话：指标正常，按时复查。',
    emphasis: ['医生原话'],
    primary: '看小结',
    why: '报告只复述医生原话',
  },
  {
    step: 'HOME',
    caption: '今天的陪诊到这儿。小结留给您，回家路上慢一点。',
    emphasis: ['小结'],
    primary: '',
    why: '陪诊单进入终态',
  },
];

const ESCALATION_TURNS = {
  sos: {
    caption: '已为您呼叫帮助，请原地别动，工作人员马上过来。',
    emphasis: ['原地别动'],
    primary: '我等着',
    why: '一键求助已发出',
  },
  'text-找不到': {
    caption: '原地别动，我请工作人员来接您。',
    emphasis: ['原地别动'],
    primary: '我等着',
    why: '用户说找不到，转服务台',
  },
};

/**
 * 创建演示会话。
 *
 * @param {{
 *   onMessage: (payload: object) => void,
 *   latency?: number,
 *   timers?: {set: Function, clear: Function},
 * }} options
 */
export function createDemoSession({ onMessage, latency = 260, timers } = {}) {
  const setTimer = timers?.set || ((fn, ms) => setTimeout(fn, ms));
  const clearTimer = timers?.clear || ((id) => clearTimeout(id));

  let cursor = 0;
  let sessionId = 's_mock';
  let episodeId = 'ep_001';
  let closed = false;
  let pending = [];

  function schedule(send) {
    if (closed) return;
    const id = setTimer(() => {
      pending = pending.filter((item) => item !== id);
      if (!closed) send();
    }, latency);
    pending.push(id);
  }

  function sendReady() {
    onMessage({
      type: 'session.ready',
      session_id: sessionId,
      episode_id: episodeId,
      protocol_version: '0.1',
      state: SCRIPT[cursor].step,
    });
  }

  function sendTurn(overrides = {}) {
    const entry = SCRIPT[cursor];
    const turn = cursor + 1;
    const flowIndex = STATUS_ORDER.indexOf(entry.step) + 1;
    const payload = {
      type: 'turn_result',
      session: sessionId,
      turn,
      caption: { text: overrides.caption ?? entry.caption, emphasis: overrides.emphasis ?? entry.emphasis },
      speech: { audio_url: '', rate: 0.86, can_interrupt: true },
      device: { vibrate: 'none', haptic_after_ms: 0 },
      flow: {
        step: entry.step,
        step_index: flowIndex,
        total: STATUS_ORDER.length,
        why: overrides.why ?? entry.why,
      },
      escalation: { level: overrides.escalation || 'none' },
      confidence: { asr: 0.93, intent: 0.9 },
      primary_label: overrides.primary ?? entry.primary,
      options: overrides.options ?? entry.options ?? [],
    };
    onMessage(payload);
  }

  function advance() {
    if (cursor < SCRIPT.length - 1) cursor += 1;
  }

  return {
    mode: 'mock',

    send(payload) {
      if (closed || !payload) return;
      switch (payload.type) {
        case 'session.hello':
          episodeId = payload.episode_id || episodeId;
          // 先回 ready，再推当前节点的一轮内容；不假设从第一步开始（协议 §2）
          schedule(() => {
            sendReady();
            sendTurn();
          });
          break;
        case 'ping':
          schedule(() => onMessage({ type: 'pong' }));
          break;
        case 'touch.event': {
          if (payload.target === 'sos') {
            const turn = ESCALATION_TURNS.sos;
            schedule(() =>
              sendTurn({
                caption: turn.caption,
                emphasis: turn.emphasis,
                primary: turn.primary,
                why: turn.why,
                escalation: 'sos',
              }),
            );
            break;
          }
          advance();
          schedule(() => sendTurn());
          break;
        }
        case 'text.input': {
          const text = String(payload.text || '').trim();
          const escalation = text.includes('找不到') ? 'call_staff' : 'none';
          const canned = escalation === 'call_staff' ? ESCALATION_TURNS['text-找不到'] : null;
          if (escalation === 'none') advance();
          schedule(() =>
            sendTurn(
              canned
                ? {
                    caption: canned.caption,
                    emphasis: canned.emphasis,
                    primary: canned.primary,
                    why: canned.why,
                    escalation,
                  }
                : {
                    caption: `您说的是「${text}」。我记下了，分诊仅作就诊参考，不能替代医生诊断。`,
                    emphasis: [text],
                    escalation,
                  },
            ),
          );
          break;
        }
        default:
          break;
      }
    },

    close() {
      closed = true;
      pending.forEach((id) => clearTimer(id));
      pending = [];
    },
  };
}
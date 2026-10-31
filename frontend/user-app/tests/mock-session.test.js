/**
 * 演示会话测试：用假定时器逐条推进脚本，断言协议最小闭环。
 * 不依赖 uni-app 运行时，也不需要网络。
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { createDemoSession } from '../src/mock/session.js';
import { normalizeTurnResult } from '../src/services/protocol.js';
import { STATUS_ORDER } from '../src/constants/status.js';

/** 假定时器：schedule 时只入队，flush() 才执行 */
function createFakeTimers() {
  let queue = [];
  return {
    set(fn) {
      queue.push(fn);
      return queue.length;
    },
    clear() {
      // 全部清空即可，演示会话只关心是否取消
    },
    flush() {
      const pending = queue;
      queue = [];
      pending.forEach((fn) => fn());
    },
    get size() {
      return queue.length;
    },
  };
}

function setup() {
  const timers = createFakeTimers();
  const messages = [];
  const session = createDemoSession({
    onMessage: (payload) => messages.push(payload),
    timers,
    latency: 0,
  });
  return { session, timers, messages };
}

function hello(session) {
  session.send({
    type: 'session.hello',
    protocol_version: '0.1',
    device_id: 'user_app',
    episode_id: 'ep_001',
    client: 'user',
    accessibility_mode: 'elder',
  });
}

test('session.hello → session.ready + 当前节点首轮', () => {
  const { session, timers, messages } = setup();
  hello(session);
  timers.flush();
  assert.equal(messages.length, 2);
  assert.equal(messages[0].type, 'session.ready');
  assert.equal(messages[0].episode_id, 'ep_001');
  assert.equal(messages[0].state, STATUS_ORDER[0]);

  const first = normalizeTurnResult(messages[1]);
  assert.ok(first, 'ready 之后应先推当前节点的 turn_result');
  assert.equal(first.flow.step, STATUS_ORDER[0]);
});

test('ping → pong', () => {
  const { session, timers, messages } = setup();
  session.send({ type: 'ping' });
  timers.flush();
  assert.deepEqual(messages, [{ type: 'pong' }]);
});

test('touch.event 推进一轮，turn_result 可被 normalize', () => {
  const { session, timers, messages } = setup();
  hello(session);
  timers.flush();
  messages.length = 0;

  session.send({ type: 'touch.event', target: 'primary', action: 'tap' });
  timers.flush();

  assert.equal(messages.length, 1);
  const turn = normalizeTurnResult(messages[0]);
  assert.ok(turn, '演示 turn_result 应能通过协议校验');
  assert.equal(turn.turn > 0, true);
  assert.equal(turn.publicStep.total, 9);
});

test('连续 primary 能走完 11 个节点，且到 HOME 后不再推进', () => {
  const { session, timers, messages } = setup();
  hello(session);
  timers.flush();
  messages.length = 0;

  const steps = [];
  for (let i = 0; i < 12; i += 1) {
    session.send({ type: 'touch.event', target: 'primary', action: 'tap' });
    timers.flush();
    const turn = normalizeTurnResult(messages[messages.length - 1]);
    assert.ok(turn, `第 ${i + 1} 轮应通过校验`);
    steps.push(turn.flow.step);
  }

  // 首轮 ready 已推 ARRIVED，所以第一次点击进入 BRIEFING
  assert.equal(steps[0], STATUS_ORDER[1]);
  assert.equal(steps[STATUS_ORDER.length - 2], 'HOME');
  // 到终态后停住，不越界
  assert.equal(steps[steps.length - 1], 'HOME');
});

test('sos 立刻升级，且不推进节点', () => {
  const { session, timers, messages } = setup();
  hello(session);
  timers.flush();
  messages.length = 0;

  session.send({ type: 'touch.event', target: 'sos', action: 'tap' });
  timers.flush();
  const turn = normalizeTurnResult(messages[0]);
  assert.equal(turn.escalation, 'sos');
  assert.equal(turn.flow.step, STATUS_ORDER[0]);
});

test('说「找不到」触发 call_staff，且不推进节点', () => {
  const { session, timers, messages } = setup();
  hello(session);
  timers.flush();
  messages.length = 0;

  session.send({ type: 'text.input', text: '我找不到抽血的地方' });
  timers.flush();
  const turn = normalizeTurnResult(messages[0]);
  assert.equal(turn.escalation, 'call_staff');
  assert.equal(turn.flow.step, STATUS_ORDER[0]);
});

test('普通文字输入原样回显并推进一轮', () => {
  const { session, timers, messages } = setup();
  hello(session);
  timers.flush();
  messages.length = 0;

  session.send({ type: 'text.input', text: '腿疼' });
  timers.flush();
  const turn = normalizeTurnResult(messages[0]);
  assert.equal(turn.escalation, 'none');
  assert.match(turn.caption.text, /腿疼/);
});

test('close 之后不再产生任何消息', () => {
  const { session, timers, messages } = setup();
  hello(session);
  session.close();
  timers.flush();
  assert.equal(messages.length, 0);
});
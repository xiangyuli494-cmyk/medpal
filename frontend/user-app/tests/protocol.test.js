/**
 * 协议纯函数测试：node --test tests/*.test.js
 *
 * 覆盖 build* / parseMessage / normalizeTurnResult / classifyMessage，
 * 用 docs/api/ws-protocol.md §4.1 的示例形状做基准。
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildAck,
  buildHello,
  buildPing,
  buildTextInput,
  buildTouch,
  classifyMessage,
  normalizeTurnResult,
  parseMessage,
} from '../src/services/protocol.js';

const TURN = {
  type: 'turn_result',
  session: 's_123',
  turn: 7,
  caption: { text: '2 楼检验科，出电梯往左', emphasis: ['2 楼', '往左'] },
  speech: { audio_url: '', rate: 0.86, can_interrupt: true },
  device: { vibrate: 'none', haptic_after_ms: 0 },
  flow: { step: 'NAVIGATE', step_index: 8, total: 11, why: '抽血要空腹' },
  escalation: { level: 'none' },
  confidence: { asr: 0.91, intent: 0.88 },
  primary_label: '我到了',
  options: [
    { id: 'dept-1', label: '检验科' },
    { id: 'dept-2', label: '放射科' },
  ],
};

test('buildHello 带协议版本与 user 客户端标识', () => {
  const hello = buildHello({ episodeId: 'ep_001', accessibilityMode: 'elder' });
  assert.equal(hello.type, 'session.hello');
  assert.equal(hello.protocol_version, '0.1');
  assert.equal(hello.client, 'user');
  assert.equal(hello.episode_id, 'ep_001');
  assert.equal(hello.accessibility_mode, 'elder');
});

test('buildHello 缺少 episodeId 时抛错', () => {
  assert.throws(() => buildHello({}), /episodeId/);
});

test('buildTouch / buildTextInput / buildAck / buildPing 形状正确', () => {
  assert.deepEqual(buildTouch({ sessionId: 's_1', target: 'primary' }), {
    type: 'touch.event',
    session: 's_1',
    target: 'primary',
    action: 'tap',
  });
  assert.deepEqual(buildTextInput({ sessionId: 's_1', text: '  腿疼  ' }), {
    type: 'text.input',
    session: 's_1',
    text: '腿疼',
  });
  assert.deepEqual(buildAck({ sessionId: 's_1', turn: 3 }), {
    type: 'ack',
    session: 's_1',
    turn: 3,
  });
  assert.deepEqual(buildPing(), { type: 'ping' });
});

test('buildTextInput 拒绝空文本', () => {
  assert.throws(() => buildTextInput({ sessionId: 's_1', text: '   ' }), /文字为空/);
});

test('parseMessage 只接受字符串 JSON 对象', () => {
  assert.deepEqual(parseMessage('{"type":"pong"}'), { type: 'pong' });
  assert.equal(parseMessage('not json'), null);
  assert.equal(parseMessage('"just a string"'), null);
  assert.equal(parseMessage(new ArrayBuffer(8)), null);
});

test('normalizeTurnResult 归一协议示例', () => {
  const turn = normalizeTurnResult(TURN);
  assert.ok(turn);
  assert.equal(turn.turn, 7);
  assert.equal(turn.caption.text, '2 楼检验科，出电梯往左');
  assert.deepEqual(turn.caption.emphasis, ['2 楼', '往左']);
  assert.equal(turn.flow.step, 'NAVIGATE');
  assert.equal(turn.flow.total, 11);
  assert.equal(turn.primaryLabel, '我到了');
  assert.equal(turn.options.length, 2);
  assert.equal(turn.escalation, 'none');
  assert.equal(turn.publicStep.index, 8);
  assert.equal(turn.publicStep.total, 9);
});

test('normalizeTurnResult 缺 flow 或缺 caption 时返回 null', () => {
  assert.equal(normalizeTurnResult({ ...TURN, flow: undefined }), null);
  assert.equal(normalizeTurnResult({ ...TURN, caption: undefined }), null);
  assert.equal(normalizeTurnResult({ ...TURN, type: 'dialog.reply' }), null);
  assert.equal(normalizeTurnResult({ ...TURN, turn: 'x' }), null);
});

test('normalizeTurnResult 过滤非法 escalation 与选项', () => {
  const turn = normalizeTurnResult({
    ...TURN,
    escalation: { level: 'panic' },
    options: [{ id: '', label: 'x' }, { id: 'a' }, { id: 'ok', label: '好的' }],
  });
  assert.equal(turn.escalation, 'none');
  assert.deepEqual(turn.options, [{ id: 'ok', label: '好的' }]);
});

test('normalizeTurnResult 选项最多保留 5 个', () => {
  const options = Array.from({ length: 8 }, (_, index) => ({
    id: `o${index}`,
    label: `选项${index}`,
  }));
  const turn = normalizeTurnResult({ ...TURN, options });
  assert.equal(turn.options.length, 5);
});

test('classifyMessage 覆盖协议下行类型', () => {
  assert.equal(classifyMessage({ type: 'session.ready' }), 'ready');
  assert.equal(classifyMessage({ type: 'turn_result' }), 'turn');
  assert.equal(classifyMessage({ type: 'dialog.reply' }), 'reply');
  assert.equal(classifyMessage({ type: 'state.transition' }), 'transition');
  assert.equal(classifyMessage({ type: 'escalation.notice' }), 'escalation');
  assert.equal(classifyMessage({ type: 'error' }), 'error');
  assert.equal(classifyMessage({ type: 'pong' }), 'pong');
  assert.equal(classifyMessage({ type: 'unknown.thing' }), 'unknown');
  assert.equal(classifyMessage(null), 'unknown');
});
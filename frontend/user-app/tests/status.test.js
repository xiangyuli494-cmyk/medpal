/**
 * 11 节点 → 9 步换算测试。
 * 基准：docs/specs/domain-model.md §2.3、docs/api/ws-protocol.md §4.1。
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildStepList,
  PUBLIC_STEPS,
  PUBLIC_TOTAL,
  STATUS_LABELS,
  STATUS_ORDER,
  statusLabel,
  toPublicStep,
} from '../src/constants/status.js';

test('状态机共 11 个节点，对外共 9 步', () => {
  assert.equal(STATUS_ORDER.length, 11);
  assert.equal(PUBLIC_STEPS.length, 9);
  assert.equal(PUBLIC_TOTAL, 9);
  assert.equal(Object.keys(STATUS_LABELS).length, 11);
});

test('前 8 个节点步序与 step_index 一致', () => {
  STATUS_ORDER.slice(0, 8).forEach((step, index) => {
    const result = toPublicStep({ step, step_index: index + 1, total: 11 });
    assert.equal(result.index, index + 1, step);
    assert.equal(result.total, 9);
    assert.equal(result.label, STATUS_LABELS[step]);
    assert.equal(result.done, false);
  });
});

test('缴费取药与看报告合并为第 9 步', () => {
  const pay = toPublicStep({ step: 'PAY_AND_PICKUP', step_index: 9, total: 11 });
  const report = toPublicStep({ step: 'REPORT', step_index: 10, total: 11 });
  assert.equal(pay.index, 9);
  assert.equal(report.index, 9);
  assert.equal(pay.done, false);
  assert.equal(report.done, false);
});

test('小结回家表示已完成', () => {
  const home = toPublicStep({ step: 'HOME', step_index: 11, total: 11 });
  assert.equal(home.index, 9);
  assert.equal(home.done, true);
  assert.equal(home.label, '已完成');
});

test('flow 缺 step_index 时按节点顺序推算', () => {
  const result = toPublicStep({ step: 'NAVIGATE' });
  assert.equal(result.index, 8);
});

test('step_index 越界时夹在 1–9', () => {
  assert.equal(toPublicStep({ step: 'ARRIVED', step_index: 0 }).index, 1);
  assert.equal(toPublicStep({ step: 'ARRIVED', step_index: 99 }).index, 9);
  assert.equal(toPublicStep({ step: 'ARRIVED', step_index: 'abc' }).index, 1);
});

test('flow 为空时不抛错', () => {
  const result = toPublicStep(undefined);
  assert.equal(result.total, 9);
  assert.ok(result.index >= 1 && result.index <= 9);
});

test('buildStepList 标出已完成 / 当前 / 未到', () => {
  const list = buildStepList(3);
  assert.equal(list.length, 9);
  assert.equal(list[0].state, 'done');
  assert.equal(list[2].state, 'current');
  assert.equal(list[3].state, 'upcoming');
});

test('buildStepList 在终态时全部标为已完成', () => {
  const list = buildStepList(9, true);
  assert.ok(list.every((item) => item.state === 'done'));
});

test('statusLabel 未知节点回退为陪诊中', () => {
  assert.equal(statusLabel('UNKNOWN'), '陪诊中');
  assert.equal(statusLabel(''), '陪诊中');
});
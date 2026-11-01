/**
 * 字幕加粗切段测试：必须保证拼回去与原文逐字相同，且 emphasis 不改变文本。
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { splitByEmphasis } from '../src/utils/highlight.js';

function join(segments) {
  return segments.map((item) => item.text).join('');
}

test('无 emphasis 时整段原样返回', () => {
  const segments = splitByEmphasis('2 楼检验科，出电梯往左');
  assert.deepEqual(segments, [{ text: '2 楼检验科，出电梯往左', strong: false }]);
});

test('命中片段被标为 strong', () => {
  const segments = splitByEmphasis('2 楼检验科，出电梯往左', ['2 楼', '往左']);
  assert.deepEqual(segments, [
    { text: '2 楼', strong: true },
    { text: '检验科，出电梯', strong: false },
    { text: '往左', strong: true },
  ]);
});

test('拼接结果与原文逐字一致', () => {
  const text = '抽血要空腹，先抽血再吃东西';
  const segments = splitByEmphasis(text, ['抽血', '空腹', '先抽血']);
  assert.equal(join(segments), text);
});

test('长词优先：重叠时整段加粗', () => {
  const segments = splitByEmphasis('先抽血再吃东西', ['抽血', '先抽血']);
  assert.deepEqual(segments, [
    { text: '先抽血', strong: true },
    { text: '再吃东西', strong: false },
  ]);
});

test('不存在的 emphasis 被忽略', () => {
  const segments = splitByEmphasis('医生原话', ['护士']);
  assert.deepEqual(segments, [{ text: '医生原话', strong: false }]);
});

test('重复 emphasis 只生效一次', () => {
  const segments = splitByEmphasis('第 12 位，第 12 位', ['第 12 位']);
  assert.equal(segments.filter((item) => item.strong).length, 2);
});

test('空文本返回空数组，非法输入不抛错', () => {
  assert.deepEqual(splitByEmphasis(''), []);
  assert.deepEqual(splitByEmphasis(null, null), []);
  assert.deepEqual(splitByEmphasis(undefined, ['x']), []);
});
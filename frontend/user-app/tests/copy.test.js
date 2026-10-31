/**
 * 文案红线测试。
 *
 * CI 的 tools/check_guard_words.py 扫全文；这里再从用户可见文案对象里
 * 逐条断言一遍，避免以后把文案挪进 .js 常量后绕过文件级扫描的直觉。
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  ACCESSIBILITY_MODES,
  CONNECTION_LABELS,
  DISCLAIMERS,
  ESCALATION_COPY,
} from '../src/constants/copy.js';

const wordsPath = fileURLToPath(new URL('../../../tools/guard_words.txt', import.meta.url));
const BANNED = readFileSync(wordsPath, 'utf8')
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter((line) => line && !line.startsWith('#'));

function collect(value, bucket = []) {
  if (typeof value === 'string') bucket.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collect(item, bucket));
  else if (value && typeof value === 'object') Object.values(value).forEach((item) => collect(item, bucket));
  return bucket;
}

test('词表可读且非空', () => {
  assert.ok(BANNED.length >= 10, `词表仅 ${BANNED.length} 条`);
});

test('用户可见文案不含禁用词', () => {
  const texts = collect([
    ACCESSIBILITY_MODES,
    CONNECTION_LABELS,
    DISCLAIMERS,
    ESCALATION_COPY,
  ]);
  const hits = [];
  for (const text of texts) {
    for (const word of BANNED) {
      if (text.includes(word)) hits.push(`${word} ← ${text}`);
    }
  }
  assert.deepEqual(hits, []);
});

test('分诊免责声明存在且措辞固定', () => {
  assert.match(DISCLAIMERS.triage, /不能替代医生诊断/);
});

test('五级升级都有文案，none 为空', () => {
  assert.deepEqual(Object.keys(ESCALATION_COPY).sort(), [
    'ask_again',
    'call_family',
    'call_staff',
    'none',
    'sos',
  ]);
  assert.equal(ESCALATION_COPY.none, '');
});
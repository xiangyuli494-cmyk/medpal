/**
 * 把字幕文本按 emphasis 切段，命中的片段加粗。
 *
 * 约束（docs/api/ws-protocol.md §4.1）：emphasis 是 text 的子串，
 * 加粗不改变文本。因此本函数必须保证 segments 拼接后与原文逐字相同。
 */

export function splitByEmphasis(text, emphasis = []) {
  const source = String(text || '');
  if (!source) return [];

  const terms = [...new Set((emphasis || []).filter((item) => typeof item === 'string' && item))]
    .filter((item) => source.includes(item))
    // 长词优先，避免「抽血」先命中导致「抽血要空腹」只加粗一半
    .sort((a, b) => b.length - a.length);

  const segments = [];
  let cursor = 0;

  while (cursor < source.length) {
    let nextIndex = -1;
    let nextTerm = '';
    for (const term of terms) {
      const found = source.indexOf(term, cursor);
      if (found === -1) continue;
      if (nextIndex === -1 || found < nextIndex || (found === nextIndex && term.length > nextTerm.length)) {
        nextIndex = found;
        nextTerm = term;
      }
    }

    if (nextIndex === -1) {
      segments.push({ text: source.slice(cursor), strong: false });
      break;
    }
    if (nextIndex > cursor) {
      segments.push({ text: source.slice(cursor, nextIndex), strong: false });
    }
    segments.push({ text: nextTerm, strong: true });
    cursor = nextIndex + nextTerm.length;
  }

  return segments;
}
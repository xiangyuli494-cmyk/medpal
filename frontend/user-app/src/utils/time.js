/** 时间格式化：小程序不保证 toLocaleTimeString 的时区输出，手动拼。 */

function pad(value) {
  return String(value).padStart(2, '0');
}

export function formatTime(date = new Date()) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

/**
 * ISO 字符串 → 「10-27 08:30」。
 * 不用 Date 解析，避免 iOS / 小程序对带时区 ISO 串的兼容差异。
 */
export function formatIsoShort(value) {
  const matched = String(value || '').match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/,
  );
  if (!matched) return String(value || '');
  return `${matched[2]}-${matched[3]} ${matched[4]}:${matched[5]}`;
}
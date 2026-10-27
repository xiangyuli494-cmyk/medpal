/**
 * 本地设置存储。
 *
 * 小程序没有 localStorage，统一走 uni 存储；调用失败时静默降级为内存值，
 * 不因为存不下就打断用户操作。
 */

const STORAGE_KEY = 'medpal:user-app:settings';

export function loadSettings() {
  try {
    const value = uni.getStorageSync(STORAGE_KEY);
    return value && typeof value === 'object' ? value : null;
  } catch {
    return null;
  }
}

export function saveSettings(value) {
  try {
    uni.setStorageSync(STORAGE_KEY, value);
    return true;
  } catch {
    return false;
  }
}

export function clearSettings() {
  try {
    uni.removeStorageSync(STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}
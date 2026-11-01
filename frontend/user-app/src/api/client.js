/**
 * 统一请求层。
 *
 * 规则（docs/plan/12 §2.4、ADR-004）：页面不得硬编码地址，只经 api/ 层；
 * 地址来自 VITE_API_BASE，经 config.js 归一。
 */

import { API_BASE } from '../config.js';

export class ApiError extends Error {
  constructor(message, { status = 0, code = '' } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/**
 * @param {string} path 以 / 开头的路径，例如 /episodes/ep_001
 * @param {{method?: string, data?: object, timeout?: number}} options
 */
export function request(path, options = {}) {
  const { method = 'GET', data, timeout = 10000 } = options;
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;

  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method,
      data,
      timeout,
      header: { Accept: 'application/json' },
      success(response) {
        const { statusCode, data: body } = response;
        if (statusCode >= 200 && statusCode < 300) {
          resolve(body);
          return;
        }
        reject(
          new ApiError(`请求失败（HTTP ${statusCode}）`, {
            status: statusCode,
            code: body?.code || '',
          }),
        );
      },
      fail(error) {
        reject(new ApiError(error?.errMsg || '网络不可用'));
      },
    });
  });
}
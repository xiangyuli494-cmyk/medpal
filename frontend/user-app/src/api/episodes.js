/**
 * 陪诊单接口。
 *
 * W1 mock 只有 GET /episodes/ep_001（tools/mock_api.py）；
 * 真实接口在 W3 由 Django 接管，路径保持不变。
 */

import { request } from './client.js';

export function fetchEpisode(episodeId) {
  if (!episodeId) throw new Error('缺少 episodeId');
  return request(`/episodes/${encodeURIComponent(episodeId)}`);
}
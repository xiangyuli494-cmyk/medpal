/**
 * 用户端构建期配置。
 *
 * 页面与组件不得直接读 import.meta.env，只从这里取。
 * 变量来源是仓库根目录 .env（vite.config.js 的 envDir）。
 * Node 下跑单测时 import.meta.env 不存在，这里退化为空对象。
 */

const env = import.meta.env || {};

function trimSlash(value) {
  return String(value || '').replace(/\/+$/, '');
}

/** REST 基地址，默认指向 W1 mock 接口 */
export const API_BASE = trimSlash(env.VITE_API_BASE) || 'http://127.0.0.1:8000/api/v1';

/** WebSocket 基地址，端点按协议拼 /ws/session/{episode_id} */
export const WS_BASE = trimSlash(env.VITE_WS_BASE) || 'ws://127.0.0.1:8090';

/** 1 = 本地 mock 会话；0 = 连真实服务 */
export const DEMO_MODE = String(env.VITE_DEMO_MODE ?? '1') !== '0';

/** 默认演示陪诊单 */
export const DEFAULT_EPISODE_ID = env.VITE_EPISODE_ID || 'ep_001';

/** 默认无障碍通道：elder / vision / hearing / standard */
export const DEFAULT_ACCESSIBILITY_MODE = env.VITE_ACCESSIBILITY_MODE || 'elder';

/** 协议版本，见 docs/api/ws-protocol.md */
export const PROTOCOL_VERSION = '0.1';

/** 客户端标识，session.hello.client 取 user */
export const CLIENT_KIND = 'user';

/** 数据流日志上限，避免长会话把内存吃满 */
export const LOG_LIMIT = 20;

/** 时间轴在进度页展示的条数 */
export const TIMELINE_LIMIT = 8;
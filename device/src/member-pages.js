const env = import.meta.env;

/**
 * 小组成员页面的默认地址。
 * 端口约定见 docs/plan/11 §4.2：
 *   用户端 5173 / 家属端 5174 / 工作台 5175 / 设备端 5176
 *
 * 可以在仓库根目录 .env 里覆盖：
 *   VITE_USER_APP_URL=http://127.0.0.1:5173
 *   VITE_FAMILY_APP_URL=http://127.0.0.1:5174
 *   VITE_CONSOLE_URL=http://127.0.0.1:5175
 */
export const MEMBER_PAGES = [
  { id: 'device', name: '设备端', kind: 'local' },
  {
    id: 'user',
    name: '用户端',
    url: env.VITE_USER_APP_URL || 'http://127.0.0.1:5173',
  },
  {
    id: 'family',
    name: '家属端',
    url: env.VITE_FAMILY_APP_URL || 'http://127.0.0.1:5174',
  },
  {
    id: 'console',
    name: '工作台',
    url: env.VITE_CONSOLE_URL || 'http://127.0.0.1:5175',
  },
];

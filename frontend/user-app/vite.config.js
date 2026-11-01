import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import uniPlugin from '@dcloudio/vite-plugin-uni';

// 本包是 "type": "module"，插件的 CJS 默认导出会多包一层；
// 不能直接 uniPlugin()，要取到里面那个函数。
const uni = typeof uniPlugin === 'function' ? uniPlugin : uniPlugin.default;

export default defineConfig({
  plugins: [uni()],
  // 仓库根目录 .env；与 device/ 共用同一批 VITE_ 变量
  envDir: '../..',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 与 device/src/member-pages.js 的 5173 约定一致，方便设备端 iframe 直接联调
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
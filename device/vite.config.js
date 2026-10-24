import { defineConfig } from 'vite';

export default defineConfig({
  // 复用仓库根目录的 .env，VITE_ 前缀变量会注入前端
  envDir: '..',
  server: {
    host: '0.0.0.0',
    port: 5176,
    strictPort: true,
  },
  preview: {
    host: '0.0.0.0',
    port: 5176,
    strictPort: true,
  },
});

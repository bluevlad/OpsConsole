import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // dev server proxy target (서버 사이드) — Docker에서는 컨테이너 DNS 'opsconsole-backend' 사용
  // host에서 직접 실행 시에는 localhost 사용
  const proxyTarget =
    env.VITE_PROXY_TARGET || env.VITE_API_BASE_URL || 'http://localhost:9100';

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 4100,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});

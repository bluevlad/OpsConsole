import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // dev server proxy target (서버 사이드) — Docker에서는 컨테이너 DNS 'opsconsole-backend' 사용
  // host에서 직접 실행 시에는 localhost 사용
  const proxyTarget =
    env.VITE_PROXY_TARGET || env.VITE_API_BASE_URL || 'http://localhost:9100';

  // 게이트웨이 도메인(예: opsconsole.unmong.com)에서 접근 시 vite 가 호스트 검증으로 막지 않도록 허용
  const allowedHostsEnv = (env.VITE_ALLOWED_HOSTS || '').trim();
  const allowedHosts = allowedHostsEnv
    ? allowedHostsEnv.split(',').map((s) => s.trim()).filter(Boolean)
    : ['localhost', '127.0.0.1', 'opsconsole.unmong.com'];

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 4100,
      allowedHosts,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});

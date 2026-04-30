import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Tauri는 webview에 file:// 또는 dev-server URL을 로드. relative path 보장.
  base: './',
  server: {
    host: '127.0.0.1',
    port: 4101,
    strictPort: true,
  },
  build: {
    target: 'es2021',
    minify: !process.env.TAURI_DEBUG,
    sourcemap: !!process.env.TAURI_DEBUG,
    outDir: 'dist',
  },
  // Tauri가 환경변수 일부 주입
  envPrefix: ['VITE_', 'TAURI_PLATFORM', 'TAURI_ARCH', 'TAURI_FAMILY', 'TAURI_PLATFORM_VERSION', 'TAURI_PLATFORM_TYPE', 'TAURI_DEBUG'],
});

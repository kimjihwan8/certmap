// 개발 서버 설정. /api 로 시작하는 요청은 Hono 서버(8790)로 넘긴다 → 화면과 API 가 같은 주소처럼 보여 CORS 설정이 필요 없다.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // MapLibre v6 는 지도 그리기용 웹 워커 파일(maplibre-gl-worker.mjs)을 자기 파일 옆에서 찾는다.
  // Vite 가 개발 중에 미리 묶으면(.vite/deps 로 옮기면) 옆에 워커가 없어 "Worker failed to load" 가 난다 → 묶지 않는다.
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8790" },
  },
});

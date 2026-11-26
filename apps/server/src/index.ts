/** 서버 실행. 사용: pnpm --filter @restaurant-map/server dev  (먼저 docker compose up -d) */
import { serve } from "@hono/node-server";
import app from "./app.js";

const PORT = Number(process.env.PORT ?? 8790);   // 8787 은 이 맥에서 다른 프로그램이 쓰고 있다

serve({ fetch: app.fetch, port: PORT }, () => {
  console.log(`API 서버 http://localhost:${PORT}/api`);
});

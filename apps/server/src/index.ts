/** 서버 실행. 사용: pnpm --filter @restaurant-map/server dev  (먼저 docker compose up -d) */
import { serve } from "@hono/node-server";
import { embedQuery, EMBED_MODEL } from "@restaurant-map/embed";
import app from "./app.js";

const PORT = Number(process.env.PORT ?? 8790);   // 8787 은 이 맥에서 다른 프로그램이 쓰고 있다

serve({ fetch: app.fetch, port: PORT }, () => {
  console.log(`API 서버 http://localhost:${PORT}/api`);
});

// 의미 검색 모델을 미리 불러 둔다. 안 그러면 첫 의미 검색이 모델 불러오기(10~20초)를 기다린다
const started = Date.now();
embedQuery("준비")
  .then(() => console.log(`의미 검색 모델 준비 (${EMBED_MODEL}, ${((Date.now() - started) / 1000).toFixed(1)}초)`))
  .catch((err) => console.error("의미 검색 모델을 못 불러왔다", err));

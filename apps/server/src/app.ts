/**
 * API 라우트. 서버 실행(index.ts)과 나눠 둔 이유: 화면(apps/web)이 이 파일의 타입(AppType)만 가져다 쓴다.
 *
 *   GET /api/tiles/:z/:x/:y   벡터 타일 (MVT 바이너리)
 *   GET /api/stores/:id       가게 상세 + 인증 목록 (JSON)
 */
import { Hono } from "hono";
import { getStore } from "./stores.js";
import { getTile, isValidTile } from "./tiles.js";

const app = new Hono()
  .basePath("/api")
  .get("/tiles/:z/:x/:y", async (c) => {
    const [z, x, y] = ["z", "x", "y"].map((k) => Number(c.req.param(k)));
    if (!isValidTile(z, x, y)) return c.text("잘못된 타일 번호", 400);
    const tile = await getTile(z, x, y);
    return c.body(new Uint8Array(tile), 200, {
      "Content-Type": "application/vnd.mapbox-vector-tile",
      // 데이터는 하루 한 번 바뀌므로 브라우저가 1시간 동안 같은 타일을 다시 요청하지 않게 한다
      "Cache-Control": "public, max-age=3600",
    });
  })
  .get("/stores/:id", async (c) => {
    const store = await getStore(c.req.param("id"));
    if (!store) return c.json({ error: "없는 가게" }, 404);
    return c.json(store, 200);
  });

// 화면이 hc<AppType>() 으로 이 타입을 쓰면, 주소·응답 모양이 서버와 어긋날 때 화면 쪽 타입 검사가 잡아낸다
export type AppType = typeof app;
export default app;

/**
 * API 라우트. 서버 실행(index.ts)과 나눠 둔 이유: 화면(apps/web)이 이 파일의 타입(AppType)만 가져다 쓴다.
 *
 *   GET /api/tiles/:z/:x/:y   벡터 타일 (MVT 바이너리)
 *   GET /api/stores/:id       가게 상세 + 인증 목록 (JSON)
 *   GET /api/stores/:id/building  같은 건물(같은 좌표)의 인증 가게 목록 (JSON)
 *   GET /api/search?q=&lat=&lon=  상호 검색 + 장소(건물 이름) (JSON)
 *   GET /api/find?lat=&lon=&certs=&cats=&q=  조건 검색: 칩으로 고른 조건을 많이 만족하는 순 (JSON)
 *   GET /api/categories       업종 칩 목록 (JSON)
 *   GET /api/parse?q=         자연어 → 칩 (규칙 v0, JSON)
 */
import { Hono } from "hono";
import { CERT_FILTERS, type CertFilter, findStores, getCategories } from "./find.js";
import { parseQuery } from "./parse.js";
import { searchPlaces, searchStores } from "./search.js";
import { getBuilding, getStore } from "./stores.js";
import { getTile, isValidTile } from "./tiles.js";

/** 한국 범위 안의 좌표인지 (위도·경도를 바꿔 넣는 실수를 잡는다) */
function inKorea(lat: number, lon: number) {
  return lat > 32 && lat < 39.5 && lon > 124 && lon < 132;
}

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
  })
  .get("/stores/:id/building", async (c) => c.json(await getBuilding(c.req.param("id")), 200))
  .get("/search", async (c) => {
    const { q = "", lat, lon } = c.req.query();
    const [la, lo] = [Number(lat), Number(lon)];
    if (!inKorea(la, lo)) return c.json({ error: "좌표가 한국 밖" }, 400);
    const text = q.slice(0, 50);
    // 가게와 장소를 동시에 찾는다 (둘은 서로 기다릴 필요가 없다)
    const [stores, places] = await Promise.all([searchStores(text, la, lo), searchPlaces(text)]);
    return c.json({ stores, places }, 200);
  })
  .get("/find", async (c) => {
    const { lat, lon, certs = "", cats = "", q = "" } = c.req.query();
    const [la, lo] = [Number(lat), Number(lon)];
    if (!inKorea(la, lo)) return c.json({ error: "좌표가 한국 밖" }, 400);
    return c.json(await findStores({
      lat: la, lon: lo, q: q.slice(0, 50),
      // 쉼표로 이은 칩 이름. 모르는 이름은 버린다
      certs: certs.split(",").filter((x): x is CertFilter => (CERT_FILTERS as string[]).includes(x)),
      cats: cats.split(",").filter((x) => x && x.length <= 30).slice(0, 50),
    }), 200);
  })
  .get("/categories", async (c) => c.json(await getCategories(), 200))
  .get("/parse", async (c) => c.json(await parseQuery((c.req.query("q") ?? "").slice(0, 100)), 200));

// 화면이 hc<AppType>() 으로 이 타입을 쓰면, 주소·응답 모양이 서버와 어긋날 때 화면 쪽 타입 검사가 잡아낸다
export type AppType = typeof app;
export type { CertFilter } from "./find.js";   // 화면의 칩 목록이 서버가 받는 칩 이름과 어긋나지 않게
export default app;

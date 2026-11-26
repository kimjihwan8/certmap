/**
 * 조건 검색 (칩). 결정 일지 9·30·32번.
 *
 * 고른 조건(인증 종류·업종)을 지도 중심 근처의 인증 가게에서 찾는다.
 * 조건을 모두 만족하는 곳만 보여주지 않는다 — 착한가격이면서 백년가게인 곳은 대전에 3곳뿐이라 대부분 비어 버린다 (결정 9번).
 * 대신 정렬: 만족한 조건 수 → 실린 공공 목록 수 → 거리. 조건을 하나도 만족하지 않는 가게는 뺀다.
 * LX 추천을 따로 앞세우지 않는다 — 그러면 'LX 추천만 맛집'이 된다 (결정 32번, 사용자 지적). LX 는 7개 목록 중 하나로 센다.
 *
 * 조건이 하나도 없으면 '이 근처 인증 가게'다: 실린 목록 수 → 거리 순. 처음 화면과 "맛집" 검색이 이걸 쓴다.
 *
 * 범위: 1km 에서 찾고 결과가 MIN_RESULTS 보다 적으면 3km → 10km → 30km 로 넓힌다.
 */
import { pool } from "./db.js";

// 칩 이름 → SQL 조건. 칩 이름은 이 목록에 있는 것만 받는다 (요청 글자를 SQL 에 그대로 넣지 않으려고)
const CERT_SQL = {
  good_price: "s.good_price",
  baengnyeon: "s.baengnyeon",
  mobum: "s.mobum",
  hygiene: "(s.hygiene OR s.ansim)",      // '위생' 칩 하나 = 식품안심업소 또는 안심식당
  lx: "s.lx",
  tour: "s.tour",
} as const;
export type CertFilter = keyof typeof CERT_SQL;
export const CERT_FILTERS = Object.keys(CERT_SQL) as CertFilter[];

const RADII = [1000, 3000, 10000, 30000];
const MIN_RESULTS = 10;
const LIMIT = 30;
const TIMEOUT_MS = 800;

export interface FindHit {
  storeId: string;
  name: string;
  branch: string | null;
  category: string | null;
  sgg: string | null;
  distance: number;
  lat: number;
  lon: number;
  certCount: number;
  lx: boolean;
  matched: string[];        // 만족한 조건 ('good_price' … 또는 'category')
  sources: string[];        // 실린 인증 원본 이름들 ('모범음식점' …). 목록에 색 배지로 보여준다
}

export interface FindResult {
  radius: number;           // 실제로 찾은 반경 (미터)
  conditions: number;       // 고른 조건 수 (업종은 여러 개 골라도 조건 1개)
  hits: FindHit[];
}

export async function findStores(p: {
  lat: number; lon: number; certs: CertFilter[]; cats: string[]; q: string;
}): Promise<FindResult> {
  const conditions = p.certs.length + (p.cats.length ? 1 : 0);

  // $1 경도, $2 위도, $3 반경. 업종·이름은 고른 경우에만 뒤에 붙인다
  // (Postgres 는 SQL 에서 안 쓰는 매개변수를 넘기면 거절하므로, 번호를 실제로 쓰는 것만 매긴다)
  const params: unknown[] = [p.lon, p.lat, 0];
  const add = (v: unknown) => `$${params.push(v)}`;

  // 만족한 조건 수 = 각 조건(참/거짓)을 0/1 로 바꿔 더한 값
  const parts = p.certs.map((c) => `(${CERT_SQL[c]})::int`);
  if (p.cats.length) parts.push(`(s.cat_small = ANY(${add(p.cats)}))::int`);
  const score = parts.length ? parts.join(" + ") : "0";   // 조건이 없으면 모두 0점 → 실린 목록 수·거리로만 정렬
  // 검색창에 글자가 있으면 이름도 같이 거른다
  const nameFilter = p.q
    ? `AND s.search_text LIKE ${add("%" + p.q.toLowerCase().replace(/\s+/g, "").replace(/[\\%_]/g, (ch) => "\\" + ch) + "%")}`
    : "";

  const sql = `
    SELECT s.store_id, s.name, s.branch, s.cat_small, s.sgg, s.lat, s.lon, s.cert_count, s.lx,
           s.good_price, s.baengnyeon, s.mobum, s.hygiene, s.ansim, s.tour,
           round(ST_Distance(s.geom, c.g))::int AS distance, (${score}) AS score,
           array(SELECT DISTINCT source FROM certs ct WHERE ct.store_id = s.store_id ORDER BY 1) AS sources
    FROM stores s, (SELECT ST_MakePoint($1, $2)::geography AS g) c
    WHERE s.cert_count > 0 AND ST_DWithin(s.geom, c.g, $3) ${conditions ? `AND (${score}) > 0` : ""} ${nameFilter}
    ORDER BY score DESC, s.cert_count DESC, distance
    LIMIT ${LIMIT}`;

  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(`SET LOCAL statement_timeout = ${TIMEOUT_MS}`);
    let rows: Record<string, any>[] = [];
    let radius = RADII[0];
    for (radius of RADII) {
      params[2] = radius;
      rows = (await client.query(sql, params)).rows;
      if (rows.length >= MIN_RESULTS) break;
    }
    await client.query("COMMIT");
    return {
      radius, conditions,
      hits: rows.map((r) => ({
        storeId: r.store_id, name: r.name, branch: r.branch, category: r.cat_small, sgg: r.sgg,
        distance: r.distance, lat: r.lat, lon: r.lon, certCount: r.cert_count, lx: r.lx,
        matched: [
          ...p.certs.filter((c) => (c === "hygiene" ? r.hygiene || r.ansim : r[c])),
          ...(p.cats.length && p.cats.includes(r.cat_small) ? ["category"] : []),
        ],
        sources: r.sources,
      })),
    };
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

/** 업종 칩에 띄울 목록: 인증 음식점의 업종 소분류와 가게 수. 하루에 한 번 바뀌는 값이라 처음 한 번만 세고 기억해 둔다. */
let categoriesCache: { name: string; count: number }[] | null = null;
export async function getCategories() {
  if (!categoriesCache) {
    const { rows } = await pool.query(
      `SELECT cat_small AS name, count(*)::int AS count FROM stores
       WHERE cert_count > 0 AND is_food AND cat_small IS NOT NULL GROUP BY 1 ORDER BY 2 DESC`,
    );
    categoriesCache = rows;
  }
  return categoriesCache!;
}

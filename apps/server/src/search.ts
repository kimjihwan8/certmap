/**
 * 상호 검색. 치는 동안 사이드바 목록이 바로 바뀐다. 결정 일지 28·29번.
 *
 * 1차는 가볍게: 이름에 검색어가 들어간 가게를 지도 중심에서 가까운 순으로 몇 개만.
 *   - 이름 거르기: search_text LIKE '%검색어%' (pg_trgm 색인. 세 글자 이상이면 색인으로 바로 찾는다)
 *   - 정렬: geom <-> 중심 (위치 색인이 가까운 곳부터 꺼내 이름을 확인하다가 LIMIT 개가 차면 멈춘다)
 *   흔한 단어는 1ms 안팎이다. 근처에 거의 없는 드문 단어는 멀리까지 훑어 느려질 수 있어 시간 제한을 건다.
 */
import { pool } from "./db.js";

export interface SearchHit {
  storeId: string;
  name: string;
  branch: string | null;
  category: string | null;
  sgg: string | null;
  distance: number;          // 지도 중심에서 미터
  lat: number;               // 사이드바 목록과 함께 지도에도 결과를 찍는다
  lon: number;
  certCount: number;         // 0 = 공공 인증 없음
  lx: boolean;
  sources: string[];         // 실린 인증 원본 이름들
}

const LIMIT = 15;           // 사이드바 목록 한 화면 분량
const TIMEOUT_MS = 300;      // 드문 단어가 0.75초까지 걸린 적이 있다 (결정 28번). 자동완성은 늦으면 의미가 없다

/** 검색어를 search_text 와 같은 모양으로: 소문자, 띄어쓰기 없음. LIKE 의 특수문자(% _ \)는 글자 그대로 찾도록 막는다. */
function toPattern(q: string): string {
  const text = q.toLowerCase().replace(/\s+/g, "");
  return "%" + text.replace(/[\\%_]/g, (ch) => "\\" + ch) + "%";
}

export async function searchStores(q: string, lat: number, lon: number): Promise<SearchHit[]> {
  if (q.replace(/\s+/g, "").length === 0) return [];
  const client = await pool.connect();
  try {
    // 이 연결의 이번 트랜잭션에만 시간 제한을 건다 (다른 쿼리에는 영향 없음)
    await client.query("BEGIN");
    await client.query(`SET LOCAL statement_timeout = ${TIMEOUT_MS}`);
    const { rows } = await client.query(
      `SELECT store_id, name, branch, cat_small, sgg, lx, cert_count, lat, lon,
              round(ST_Distance(geom, center))::int AS distance,
              array(SELECT DISTINCT source FROM certs ct WHERE ct.store_id = stores.store_id ORDER BY 1) AS sources
       FROM stores, (SELECT ST_MakePoint($3, $2)::geography AS center) c
       WHERE search_text LIKE $1 AND geom IS NOT NULL   -- 좌표 없는 가게(지오코딩 대기)는 지도에 띄울 수 없어 뺀다
       ORDER BY geom <-> center
       LIMIT ${LIMIT}`,
      [toPattern(q), lat, lon],
    );
    await client.query("COMMIT");
    return rows.map((r) => ({
      storeId: r.store_id, name: r.name, branch: r.branch, category: r.cat_small, sgg: r.sgg,
      distance: r.distance, lat: r.lat, lon: r.lon, certCount: r.cert_count, lx: r.lx, sources: r.sources,
    }));
  } catch (err) {
    await client.query("ROLLBACK");
    // 시간 초과(57014)면 오류 대신 빈 결과. 자동완성 하나 못 보여주는 것보다 화면이 멈추는 게 더 나쁘다
    if ((err as { code?: string }).code === "57014") return [];
    throw err;
  } finally {
    client.release();
  }
}

/**
 * 장소 찾기: 상가의 건물 이름이 검색어와 정확히 같은 곳. 결정 일지 11번.
 * 좌표는 그 건물에 있는 가게들의 평균. LLM 이나 지도 API 에 묻지 않고 우리 데이터에서 찾는다.
 * '정확히 같은' 이름만 쓰는 이유: '대전역'이 들어간 이름으로 찾으면 '서대전역코아루써밋' 같은 아파트가 섞인다.
 */
export interface PlaceHit {
  name: string;
  sgg: string | null;
  lat: number;
  lon: number;
  stores: number;            // 그 건물에 있는 가게 수 (같은 이름의 건물이 여러 곳이면 큰 곳 먼저)
}

export async function searchPlaces(q: string): Promise<PlaceHit[]> {
  const text = q.replace(/\s+/g, "");
  if (text.length < 2) return [];
  const { rows } = await pool.query(
    `SELECT min(bldg_name) AS name, sgg, avg(lat) AS lat, avg(lon) AS lon, count(*)::int AS stores
     FROM stores
     WHERE replace(bldg_name, ' ', '') = $1 AND bldg_name IS NOT NULL AND lat IS NOT NULL
     GROUP BY sgg ORDER BY stores DESC LIMIT 3`,
    [text],
  );
  return rows.map((r) => ({ name: r.name, sgg: r.sgg, lat: r.lat, lon: r.lon, stores: r.stores }));
}

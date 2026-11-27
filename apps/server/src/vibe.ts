/**
 * 의미 검색: "분위기 좋은", "데이트하기 좋은"처럼 칩으로 못 읽는 말을 관광공사 소개글에서 찾는다. 결정 일지 33·37번.
 *
 * 1. 검색어 → 벡터 (packages/embed, bge-m3 — DB 의 소개글 벡터와 같은 모델)
 * 2. 기준점 근처에서 소개글 벡터가 가까운 순 TOP 곳 (근처에 너무 적으면 범위를 넓힌다)
 * 3. 근거 문장: 고른 가게의 소개글을 문장으로 나눠 다시 임베딩하고, 검색어와 가장 가까운 문장을 고른다
 *    정밀도가 62% 라 틀린 결과도 나온다. 근거 문장을 보여주면 사용자가 맞는지 직접 판단할 수 있다
 *
 * 소개글이 있는 가게(관광공사 목록)만 걸린다. 그 밖의 가게는 이 검색으로 찾을 수 없다 (결정 24번).
 * 칩을 골랐으면 그 조건을 모두 만족하는 가게 안에서만 찾는다 ("분위기 좋은 국밥집" → 국밥집 중에서 분위기).
 */
import { embedPassages, embedQuery, toVectorLiteral } from "@restaurant-map/embed";
import { pool } from "./db.js";
import { CERT_SQL, type CertFilter } from "./find.js";

export interface VibeHit {
  storeId: string;
  name: string;
  branch: string | null;
  category: string | null;
  sgg: string | null;
  distance: number;
  lat: number;
  lon: number;
  sources: string[];
  evidence: string;          // 검색어와 가장 가까운 소개글 문장
}

const TOP = 5;
const MIN_RESULTS = 3;
const RADII = [5000, 20000, 60000];   // 이 안에 MIN_RESULTS 곳이 안 되면 넓힌다. 그래도 없으면 전국
const MAX_SENTENCES = 12;              // 가게 하나에서 근거 후보로 볼 문장 수 (너무 길면 임베딩이 느려진다)

const dot = (a: number[], b: number[]) => a.reduce((s, x, i) => s + x * b[i], 0);   // 길이 1 벡터끼리는 내적 = 코사인

/** 소개글 → 문장들. 마침표 뒤에서 자른다. 맨 앞의 가게 이름(store_texts 를 만들 때 붙인 것)과 너무 짧은 조각은 뺀다 */
function sentences(text: string, name: string): string[] {
  return text.split(/(?<=[.!?])\s+/).map((s) => s.trim())
    .filter((s) => s.length >= 8 && s.replace(/\.$/, "") !== name)
    .slice(0, MAX_SENTENCES);
}

export async function searchVibe(p: {
  q: string; lat: number; lon: number; certs: CertFilter[]; cats: string[];
}): Promise<{ radius: number | null; hits: VibeHit[] }> {
  const qv = await embedQuery(p.q);
  const params: unknown[] = [toVectorLiteral(qv), p.lon, p.lat];
  const add = (v: unknown) => `$${params.push(v)}`;
  // 칩 조건: 고른 것을 모두 만족해야 한다 (조건 검색과 달리 여기서는 거르기 — 근거 문장으로 보여줄 목록이 짧아서)
  const chipFilter = [
    ...p.certs.map((c) => `AND ${CERT_SQL[c]}`),
    ...(p.cats.length ? [`AND s.cat_small = ANY(${add(p.cats)})`] : []),
  ].join(" ");
  const radiusParam = `$${params.length + 1}`;   // 반경은 맨 뒤에 붙인다 (전국 검색에서는 안 쓴다)
  const sql = (withinRadius: boolean) => `
    SELECT s.store_id, s.name, s.branch, s.cat_small, s.sgg, s.lat, s.lon, t.text,
           round(ST_Distance(s.geom, c.g))::int AS distance,
           array(SELECT DISTINCT source FROM certs ct WHERE ct.store_id = s.store_id ORDER BY 1) AS sources
    FROM store_texts t JOIN stores s USING (store_id), (SELECT ST_MakePoint($2, $3)::geography AS g) c
    WHERE s.geom IS NOT NULL ${chipFilter} ${withinRadius ? `AND ST_DWithin(s.geom, c.g, ${radiusParam})` : ""}
    ORDER BY t.embedding <=> $1::vector
    LIMIT ${TOP}`;

  let rows: Record<string, any>[] = [];
  let radius: number | null = null;
  for (const r of RADII) {
    rows = (await pool.query(sql(true), [...params, r])).rows;
    radius = r;
    if (rows.length >= MIN_RESULTS) break;
  }
  if (rows.length < MIN_RESULTS) {
    rows = (await pool.query(sql(false), params)).rows;
    radius = null;   // 전국
  }

  // 근거 문장: 고른 가게들의 문장을 한 번에 임베딩해서 (가게마다 따로 부르는 것보다 빠르다) 가게별로 가장 가까운 문장
  const split = rows.map((r) => sentences(r.text, r.name));
  const flat = split.flat();
  const vecs = flat.length ? await embedPassages(flat) : [];
  let k = 0;
  const hits = rows.map((r, i) => {
    let best = "", bestScore = -1;
    for (const s of split[i]) {
      const score = dot(qv, vecs[k++]);
      if (score > bestScore) [best, bestScore] = [s, score];
    }
    return {
      storeId: r.store_id, name: r.name, branch: r.branch, category: r.cat_small, sgg: r.sgg,
      distance: r.distance, lat: r.lat, lon: r.lon, sources: r.sources, evidence: best,
    };
  });
  return { radius, hits };
}

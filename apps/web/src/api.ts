/**
 * API 클라이언트. 서버(apps/server)의 라우트 타입(AppType)을 그대로 가져다 쓴다 (Hono RPC, 결정 일지 27번).
 * 서버에서 주소나 응답 모양을 바꾸면 이 파일을 쓰는 화면 코드에서 타입 오류가 난다 → 서버·화면이 어긋날 수 없다.
 */
import { hc } from "hono/client";
import type { AppType, CertFilter } from "@restaurant-map/server";

export type { CertFilter };

const client = hc<AppType>("/");

/** 가게 상세. 없는 가게면 null. */
export async function fetchStore(id: string) {
  const res = await client.api.stores[":id"].$get({ param: { id } });
  if (!res.ok) {
    if (res.status === 404) return null;
    // 서버 타입에는 200·404 만 있지만, 서버가 죽었을 때(500 등)도 여기로 온다
    throw new Error("가게 정보를 못 불러왔어요");
  }
  return res.json();
}

export type StoreDetail = NonNullable<Awaited<ReturnType<typeof fetchStore>>>;

/** 상호 검색 + 장소(건물 이름). 가게는 지도 중심(lat, lon)에서 가까운 순 */
export async function searchStores(q: string, lat: number, lon: number) {
  const res = await client.api.search.$get({ query: { q, lat: String(lat), lon: String(lon) } });
  if (!res.ok) throw new Error("검색하지 못했어요");
  return res.json();
}

export type SearchHit = Awaited<ReturnType<typeof searchStores>>["stores"][number];
export type PlaceHit = Awaited<ReturnType<typeof searchStores>>["places"][number];

/** 조건 검색 (칩): 고른 조건을 많이 만족하는 순 */
export async function findStores(p: { lat: number; lon: number; certs: CertFilter[]; cats: string[]; q: string }) {
  const res = await client.api.find.$get({
    query: { lat: String(p.lat), lon: String(p.lon), certs: p.certs.join(","), cats: p.cats.join(","), q: p.q },
  });
  if (!res.ok) throw new Error("조건으로 찾지 못했어요");
  return res.json();
}

export type FindResult = Awaited<ReturnType<typeof findStores>>;

/** 업종 칩 목록 (인증 음식점의 업종 소분류와 가게 수) */
export async function fetchCategories() {
  const res = await client.api.categories.$get();
  if (!res.ok) throw new Error("업종 목록을 못 불러왔어요");
  return res.json();
}

/** 이 가게와 같은 건물(같은 좌표)의 인증 가게 목록 */
export async function fetchBuilding(id: string) {
  const res = await client.api.stores[":id"].building.$get({ param: { id } });
  if (!res.ok) throw new Error("건물 목록을 못 불러왔어요");
  return res.json();
}

export type BuildingStore = Awaited<ReturnType<typeof fetchBuilding>>[number];

/** 자연어 → 칩 (규칙 v0). "대전역 근처 싼 노포" → 장소 + 칩 */
export async function parseQuery(q: string) {
  const res = await client.api.parse.$get({ query: { q } });
  if (!res.ok) throw new Error("검색어를 해석하지 못했어요");
  return res.json();
}

export type ParseResult = Awaited<ReturnType<typeof parseQuery>>;

/** 의미 검색: 관광공사 소개글에서 "분위기 좋은" 같은 말과 가까운 가게 + 근거 문장 */
export async function searchVibe(p: { q: string; lat: number; lon: number; certs: CertFilter[]; cats: string[] }) {
  const res = await client.api.vibe.$get({
    query: { q: p.q, lat: String(p.lat), lon: String(p.lon), certs: p.certs.join(","), cats: p.cats.join(",") },
  });
  if (!res.ok) throw new Error("소개글 검색을 하지 못했어요");
  return res.json();
}

export type VibeResult = Awaited<ReturnType<typeof searchVibe>>;

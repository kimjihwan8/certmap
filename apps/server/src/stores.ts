/** 가게 상세: 가게 정보 + 붙은 인증 목록. 지도에서 점을 눌렀을 때 쓴다. */
import { pool } from "./db.js";

// 이 타입들이 Hono RPC 로 화면(apps/web)까지 그대로 전달된다. 바꾸면 화면 쪽 타입 검사가 바로 알려준다.
export interface StoreDetail {
  storeId: string;
  origin: "sangga" | "cert";        // 상가 가게인지, 상가에 없어 인증으로 만든 가게인지
  name: string;
  branch: string | null;
  category: string | null;          // 상가 업종 소분류 ('국/탕/찌개류' …)
  roadKey: string | null;           // 건물 키 '시도|도로명|본번-부번'
  floor: string | null;
  lat: number;
  lon: number;
  coordSource: string;              // 좌표 출처 (sangga / building / source …)
  certCount: number;
  buildingCount: number;            // 같은 좌표(같은 건물)에 있는 인증 가게 수, 이 가게 포함. 2 이상이면 화면이 목록 버튼을 띄운다
  certs: Cert[];
}

/** 건물 목록의 한 줄 */
export interface BuildingStore {
  storeId: string;
  name: string;
  branch: string | null;
  category: string | null;
  floor: string | null;
  certCount: number;
  lx: boolean;
  sources: string[];                // 붙은 인증 원본 이름들 ('모범음식점' …)
}

// 같은 좌표 찾기: 좌표가 완전히 같은 가게끼리 묶는다(타일과 같은 기준).
// '=' 대신 0.5m 상자(&&)로 찾는 이유: && 는 위치 색인을 쓰고, = 는 못 쓴다
const SAME_SPOT = `s.geom_3857 && ST_Expand((SELECT geom_3857 FROM stores WHERE store_id = $1), 0.5)`;

export interface Cert {
  source: string;                   // '모범음식점' 등
  name: string;                     // 인증 원본의 이름 (상가 상호와 다를 수 있다)
  addr: string | null;
  menu: string | null;
  certDate: string | null;          // 'YYYY-MM-DD'
  validTo: string | null;
  sinceYear: number | null;
}

/** 가게 하나. 없으면 null. */
export async function getStore(storeId: string): Promise<StoreDetail | null> {
  const store = await pool.query(
    `SELECT store_id, origin, name, branch, cat_small, road_key, floor, lat, lon, coord_source, cert_count
     FROM stores WHERE store_id = $1`,
    [storeId],
  );
  if (store.rowCount === 0) return null;
  const s = store.rows[0];
  // 날짜는 to_char 로 글자로 받는다. pg 는 date 를 자바스크립트 Date 로 바꾸는데, 이때 시간대 때문에 하루가 밀릴 수 있다.
  const certs = await pool.query(
    `SELECT source, name, addr, menu,
            to_char(cert_date, 'YYYY-MM-DD') AS cert_date, to_char(valid_to, 'YYYY-MM-DD') AS valid_to, since_year
     FROM certs WHERE store_id = $1 ORDER BY source`,
    [storeId],
  );
  const building = await pool.query(
    `SELECT count(*)::int AS n FROM stores s WHERE ${SAME_SPOT} AND s.cert_count > 0`,
    [storeId],
  );
  return {
    storeId: s.store_id, origin: s.origin, name: s.name, branch: s.branch, category: s.cat_small,
    roadKey: s.road_key, floor: s.floor, lat: s.lat, lon: s.lon, coordSource: s.coord_source,
    certCount: s.cert_count,
    buildingCount: building.rows[0].n,
    certs: certs.rows.map((c) => ({
      source: c.source, name: c.name, addr: c.addr, menu: c.menu,
      certDate: c.cert_date, validTo: c.valid_to, sinceYear: c.since_year,
    })),
  };
}

/** 이 가게와 같은 좌표(같은 건물)에 있는 인증 가게들. 실린 목록 수 → 이름 순. */
export async function getBuilding(storeId: string): Promise<BuildingStore[]> {
  const { rows } = await pool.query(
    `SELECT s.store_id, s.name, s.branch, s.cat_small, s.floor, s.cert_count, s.lx,
            array(SELECT DISTINCT source FROM certs c WHERE c.store_id = s.store_id ORDER BY 1) AS sources
     FROM stores s
     WHERE ${SAME_SPOT} AND s.cert_count > 0
     ORDER BY s.cert_count DESC, s.name`,
    [storeId],
  );
  return rows.map((r) => ({
    storeId: r.store_id, name: r.name, branch: r.branch, category: r.cat_small, floor: r.floor,
    certCount: r.cert_count, lx: r.lx, sources: r.sources,
  }));
}

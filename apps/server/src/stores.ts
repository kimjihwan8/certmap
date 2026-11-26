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
  certs: Cert[];
}

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
  return {
    storeId: s.store_id, origin: s.origin, name: s.name, branch: s.branch, category: s.cat_small,
    roadKey: s.road_key, floor: s.floor, lat: s.lat, lon: s.lon, coordSource: s.coord_source,
    certCount: s.cert_count,
    certs: certs.rows.map((c) => ({
      source: c.source, name: c.name, addr: c.addr, menu: c.menu,
      certDate: c.cert_date, validTo: c.valid_to, sinceYear: c.since_year,
    })),
  };
}

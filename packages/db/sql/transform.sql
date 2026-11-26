-- staging(CSV 그대로, 전부 글자) → 서비스용 표(stores, certs). load.ts 가 schema.sql 다음에 실행한다.
--
-- staging 표는 CSV 머리줄의 열 이름 그대로다:
--   staging.sangga      상가 277만 (prep_sangga.py)
--   staging.certs       인증 83,922 (prep_certs.py)
--   staging.matches     1단계 판정 상세: 후보를 찾은 건물 키 (match_all.py)
--   staging.cert_store  모든 인증의 최종 가게 번호 (match_stage2.py)
--   staging.new_stores  상가에 없어 인증으로 만든 가게 (match_stage2.py)
--
-- CSV 의 빈 칸은 COPY 가 처음부터 NULL 로 넣는다 (빈 글자 '' 가 아니다).
-- 그래서 'x = 값' 비교는 빈 칸이면 NULL 이 된다 → true/false 가 꼭 필요한 열은 COALESCE 로 false 를 준다.

-- 1-1. 상가 가게: 음식점 전부 + 음식점이 아니어도 인증이 붙은 가게
--      음식점만 먼저 거르면 상가 업종이 잘못 적힌 인증 식당이 빠진다 (결정 6·12번). 그래서 매칭 결과로 한 번 더 살린다.
INSERT INTO stores (store_id, origin, name, branch, name_norm, cat_large, cat_mid, cat_small,
                    sido, sgg, road_key, bldg_name, floor, lat, lon, coord_source, is_food)
SELECT s.store_id, 'sangga', s.name_raw, s.branch_raw, s.name_norm,
       s.cat_large, s.cat_mid, s.cat_small, s.sido, s.sgg,
       s.road_key, s.bldg_name, s.floor,
       s.lat::double precision, s.lon::double precision, 'sangga',
       COALESCE(s.cat_large = '음식', false)
FROM staging.sangga s
WHERE s.cat_large = '음식'
   OR s.store_id IN (SELECT store_id FROM staging.cert_store WHERE stage = '1');

-- 1-2. 상가에 없는 가게 (2단계에서 만든 새 가게)
--      is_food: 백년가게만 원본에서 음식점을 거르지 못했다(업종 열이 없음). 다른 소스가 하나라도 있으면 음식점이다.
INSERT INTO stores (store_id, origin, name, branch, name_norm, sido, sgg, road_key,
                    lat, lon, coord_source, is_food)
SELECT n.store_id, 'cert', n.name, n.branch, n.name_norm, n.sido, n.sgg, n.road_key,
       n.lat::double precision, n.lon::double precision, n.coord_source,
       CASE WHEN n.sources = '백년가게' THEN NULL ELSE true END
FROM staging.new_stores n;

-- 2. 인증: 최종 가게 번호(cert_store)와 1단계 상세(matches)를 붙여 넣는다
INSERT INTO certs (cert_id, store_id, source, name, branch, addr, sido, sgg, tel, food, menu,
                   cert_date, valid_to, license_no, since_year, lat, lon, is_chain,
                   match_stage, match_reason, match_found_by)
SELECT c.cert_id, cs.store_id, c.source, c.name_raw, c.branch,
       c.addr_raw, c.sido, c.sgg_city, c.tel,
       c.food_raw, c.menu,
       c.cert_date::date, c.valid_to::date,
       c.license_no, c.since_year::smallint,
       c.lat::double precision, c.lon::double precision,
       COALESCE(c.is_chain = '1', false),
       cs.stage::smallint, cs.how, m.found_by
FROM staging.certs c
JOIN staging.cert_store cs USING (cert_id)
JOIN staging.matches m USING (cert_id);

-- 3. 체크 열과 cert_count 를 certs 에서 계산해 채운다
--    가게마다 붙은 소스 목록을 배열로 모은 뒤('모범음식점' = ANY(배열)), 배열 길이를 cert_count 로 쓴다.
UPDATE stores s SET
    mobum      = '모범음식점'   = ANY(a.sources),
    good_price = '착한가격업소' = ANY(a.sources),
    baengnyeon = '백년가게'     = ANY(a.sources),
    tour       = '관광공사'     = ANY(a.sources),
    hygiene    = '식품안심업소' = ANY(a.sources),
    ansim      = '안심식당'     = ANY(a.sources),
    lx         = 'LX공사맛집'   = ANY(a.sources),
    cert_count = cardinality(a.sources)
FROM (SELECT store_id, array_agg(DISTINCT source) AS sources FROM certs GROUP BY store_id) a
WHERE s.store_id = a.store_id;

-- 4. 색인: 데이터를 다 넣은 뒤에 만든다 (넣기 전에 만들면 행마다 색인을 고쳐서 느리다)
CREATE INDEX stores_geom_idx ON stores USING gist (geom);           -- "이 좌표 반경 1km 안" 을 빠르게
-- 벡터 타일용: 인증 가게만 담은 부분 색인 (기본 지도는 인증 가게만 그린다. 결정 27번)
CREATE INDEX stores_tile_idx ON stores USING gist (geom_3857) WHERE cert_count > 0;
CREATE INDEX stores_cert_idx ON stores (cert_count) WHERE cert_count > 0;  -- 인증 가게만 고를 때
CREATE INDEX certs_store_idx ON certs (store_id);                   -- 가게 상세 화면에서 인증 목록 찾기

-- 5. 다 옮겼으니 staging 을 지우고, 통계를 갱신한다 (Postgres 가 쿼리 계획을 잘 세우도록)
DROP SCHEMA staging CASCADE;
ANALYZE stores;
ANALYZE certs;

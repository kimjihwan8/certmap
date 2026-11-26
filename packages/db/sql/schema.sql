-- 서비스용 표 두 개. 결정 일지 12·20번.
--
--   stores  가게 1곳 = 1행. 지도에 찍히고 검색되는 단위.
--   certs   인증 1건 = 1행. 어느 가게에 붙었는지(store_id)와 인증 상세(지정일·메뉴·유효기간…).
--
-- 체크 열(mobum, good_price …)과 cert_count 는 certs 에서 계산해 채운다 (transform.sql).
-- 손으로 따로 고치지 않는다 — 두 표가 어긋나지 않게 하려고.
--
-- 이 파일은 실행할 때마다 표를 지우고 새로 만든다. DB는 CSV에서 언제든 다시 만들 수 있는 결과물이라서다.

CREATE EXTENSION IF NOT EXISTS postgis;   -- 위치: 좌표 자료형, 반경 검색, 공간 색인
CREATE EXTENSION IF NOT EXISTS vector;    -- 의미 검색: 임베딩 자료형 (5단계에서 열 추가)
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- 상호 검색: 글자 3개 묶음(trigram) 색인. 결정 28번

DROP TABLE IF EXISTS certs;
DROP TABLE IF EXISTS stores;

CREATE TABLE stores (
    store_id    text PRIMARY KEY,           -- 상가업소번호. 상가에 없는 인증 가게는 'C-' + 인증 번호 (match_stage2.py)
    origin      text NOT NULL,              -- 'sangga' = 상가 가게, 'cert' = 상가에 없어 인증으로 만든 가게
    name        text NOT NULL,              -- 상호명 (원래 표기)
    branch      text,                       -- 지점명
    name_norm   text,                       -- 비교·검색용 이름 (normalize.py 의 name_norm). 상호가 '주식회사'뿐이면 다 떼여 빈칸
    -- 상호 검색용 글자: 상호 + 지점명을 소문자로, 띄어쓰기 없이. '성심당 본점'으로 쳐도 상호 '성심당' + 지점 '본점'이 찾아진다
    search_text text GENERATED ALWAYS AS
                    (lower(replace(name || coalesce(branch, ''), ' ', ''))) STORED,
    cat_large   text,                       -- 업종 대분류 ('음식', '소매' …). origin='cert' 는 상가 업종이 없어 빈칸
    cat_mid     text,                       -- 업종 중분류 ('한식', '주점' …)
    cat_small   text,                       -- 업종 소분류 ('국/탕/찌개류' …). 음식은 43종
    sido        text,
    sgg         text,
    road_key    text,                       -- 건물 키 '시도|도로명|본번-부번' (주소 표시에도 쓴다)
    bldg_name   text,
    floor       text,
    lat         double precision,           -- 빈칸 = 지오코딩 전 (결정 23번)
    lon         double precision,
    coord_source text,                      -- 좌표 출처: sangga(상가 원본) / building(같은 건물 상가 가게) / source(인증 원본) / vworld / kakao
    -- 좌표를 PostGIS 자료형으로. lat·lon 에서 자동으로 계산되므로 따로 넣을 필요가 없다 (GENERATED).
    -- geography = 지구 위의 점. 거리를 미터 단위로 바로 잴 수 있다 ("대전역 반경 1km").
    geom        geography(Point, 4326) GENERATED ALWAYS AS
                    (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED,
    -- 같은 좌표를 웹 지도 타일 좌표계(웹 메르카토르, EPSG:3857)로. 벡터 타일을 만들 때 쓴다.
    -- 타일 요청마다 변환하지 않도록 미리 계산해 두고 색인을 건다 (결정 27번).
    geom_3857   geometry(Point, 3857) GENERATED ALWAYS AS
                    (ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 3857)) STORED,
    is_food     boolean,                    -- 음식점인가. 상가 가게는 대분류 '음식'이면 true (정육점 등은 false).
                                            -- origin='cert' 는 음식점만 거른 소스의 인증이 있으면 true, 백년가게뿐이면 빈칸(모름)

    -- 인증 체크 열: 이 가게에 그 인증이 붙어 있으면 true
    mobum       boolean NOT NULL DEFAULT false,   -- 모범음식점
    good_price  boolean NOT NULL DEFAULT false,   -- 착한가격업소
    baengnyeon  boolean NOT NULL DEFAULT false,   -- 백년가게
    tour        boolean NOT NULL DEFAULT false,   -- 관광공사
    hygiene     boolean NOT NULL DEFAULT false,   -- 식품안심업소
    ansim       boolean NOT NULL DEFAULT false,   -- 안심식당
    lx          boolean NOT NULL DEFAULT false,   -- LX 공사맛집 (인증 아님, 추천)
    cert_count  smallint NOT NULL DEFAULT 0       -- 붙은 소스 종류 수 (같은 소스 2건은 1로 센다). 결정 10번 정렬 기준
);

CREATE TABLE certs (
    cert_id     text PRIMARY KEY,           -- 'MB-…', 'GP-…' (prep_certs.py 가 만든 번호)
    store_id    text NOT NULL REFERENCES stores,  -- 붙은 가게 (1단계 상가 매칭 또는 2단계)
    source      text NOT NULL,              -- '모범음식점' 등
    name        text NOT NULL,              -- 인증 원본의 이름
    branch      text,
    addr        text,                       -- 인증 원본의 주소
    sido        text,
    sgg         text,
    tel         text,
    food        text,                       -- 원본의 업종·음식 유형
    menu        text,
    cert_date   date,                       -- 지정일
    valid_to    date,                       -- 만료일 (식품안심업소만)
    license_no  text,                       -- 인허가번호 (모범음식점·식품안심업소)
    since_year  smallint,                   -- 인허가 연도 ("노포" 판단 후보)
    lat         double precision,           -- 원본 좌표 (관광공사만)
    lon         double precision,
    is_chain    boolean NOT NULL,           -- 같은 소스에 같은 본이름 5곳 이상 (프랜차이즈 추정)
    match_stage    smallint NOT NULL,       -- 1 = 상가에 붙음 (match_all.py), 2 = 물려받기·새 가게 (match_stage2.py)
    match_reason   text NOT NULL,           -- 1단계: v1 판정 이유 (same, near_food …) / 2단계: inherit_license, new_group …
    match_found_by text                     -- 후보를 찾은 건물 키 (road / jibun)
);

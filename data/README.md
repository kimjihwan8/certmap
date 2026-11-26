# 원본 데이터

`raw/` 에는 받은 그대로의 원본을 둔다(식별정보 열 제외). 전처리는 이 파일들만 읽는다.

| 인증 | 파일 | 출처 | 인코딩 | 원본 행 | 유효 기준 → 건수 |
|---|---|---|---|---|---|
| 모범음식점 | `모범음식점_20261021.csv` | [data.go.kr 15076765](https://www.data.go.kr/data/15076765/fileData.do) (API: 15155052) | CP949 | 65,428 | 영업 + 지정취소 없음(또는 취소 후 재지정) → 11,560 |
| 착한가격업소 | `착한가격업소_20260930.csv` | [data.go.kr 3045247](https://www.data.go.kr/data/3045247/fileData.do) | UTF-8 BOM | 12,935 | 업종이 음식점 6종 → 9,710 |
| 백년가게 | `백년가게_20260820.csv` | [data.go.kr 15132695](https://www.data.go.kr/data/15132695/fileData.do) | CP949 | 1,511 | 전 업종 섞임, 식당 판별 필요 |
| 관광공사 맛집 | `관광공사_음식점_20261022.json` | [data.go.kr 15101578](https://www.data.go.kr/data/15101578/openapi.do) `areaBasedList2`, contentTypeId=39 | UTF-8 | 13,408 | 카페(FD05) 3,044건 포함 |
| 식품안심업소 | `식품안심업소_20261026.csv` | [식품안전나라 C004](https://www.foodsafetykorea.go.kr/api/openApiInfo.do?menu_grp=MENU_GRP31&menu_no=661&show_cnt=10&start_idx=1&svc_no=C004) | UTF-8 | 46,896 | 정상 + 미취소 + 유효기간 내 → 45,285 (같은 상호 5곳 이상 19,895) |
| 안심식당 | `안심식당_대전만_20261027.csv` (**대전만, 전국 아님**) | [data.mafra.go.kr](https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do) | UTF-8 (원본 CP949) | 990 | 선정여부 Y → 744. 전국은 `scripts/fetch_ansim.py` 로 받아야 함 |
| LX 공사맛집 (추천) | `LX공사맛집_20260310.csv` | [data.go.kr 15117214](https://www.data.go.kr/data/15117214/fileData.do) | CP949 | 2,013 | 인증 아님. 직원 추천 목록. 영업시간·주차·제안수·댓글수는 사실상 빈 열. 주소 일부가 옛 행정구역(청원군·경북 군위군) → prep_certs 에서 고침 |
| 상가(상권)정보 | `~/Downloads/맛집 프로젝트 공공데이터/소상공인시장진흥공단_상가(상권)정보_20260630/` | 소상공인시장진흥공단 | UTF-8 | 2,772,484 | 17개 시도 CSV |

## 주의

- 식품안심업소: 대표자명(`PRSDNT_NM`)·사업자등록번호(`WRKR_REG_NO`)는 복사할 때 뺐다. 원본은 2026-10-26 기준 주소가 온전하다(참고 레포가 겪은 8월 주소 절단은 해소됨)
- 안심식당 API: `RELAX_SI_NM`=시도, `RELAX_SIDO_NM`=시군구 (이름과 반대). 대표자 실명 열은 저장하지 않는다. 파일 다운로드본은 열 이름이 한글(`시도명`·`시군구명`·`사업장명`·`선정여부`)이고 취소일 빈값이 문자열 `null`
- 관광공사는 인증이 아니라 편집 선정이다

# 전처리 결과 (`processed/`)

실행 순서: `python3 scripts/prep_sangga.py` (약 30초) → `python3 scripts/prep_certs.py` (약 2초).
정규화 규칙은 `scripts/normalize.py` 한 곳에 있고 `python3 scripts/normalize.py` 로 자체 테스트한다.

| 파일 | 내용 |
|---|---|
| `sangga.csv` | ② 상가 정제 표 2,772,484행 (약 800MB). 업종으로 거르지 않음 |
| `sgg_known.json` | 시도별 시군구 목록 (인증 쪽 시군구 보정용) |
| `certs.csv` | ① 인증 공통 표 83,922행 (인증 6종 + LX 추천, 안심식당은 대전만) |

- 건물 키(`road_key`) = `시도|도로명|본번-부번`. 시군구는 키에서 뺐다(인천 구 개편 등으로 소스마다 다름) — 매칭 때 `sgg_city` 로 따로 비교
- 모범음식점·식품안심업소의 `license_no`(인허가번호)는 같은 체계다. 공통 717건 중 716건이 건물 키도 같음 → 인증끼리 잇는 확실한 열쇠이자 주소 파싱 일관성 검증
- `is_chain` = 같은 소스에서 같은 본이름 5곳 이상. 표시만 하고 지우지 않음

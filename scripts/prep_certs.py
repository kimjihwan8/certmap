"""인증 원본 7종 → data/processed/certs.csv (① 인증 공통 표)

7종 = 정부·공공기관 인증 6종 + LX 공사맛집(추천 목록). 편의상 모두 "인증"이라 부른다.

하는 일:
    1. 소스마다 원본 파일을 읽는다                        (load_* 함수 7개)
    2. 지금 유효한 인증만 남긴다 (폐업·취소·만료·비식당 거르기) (load_* 함수 안에서)
    3. 7종을 같은 열 구성(COLS)으로 바꾼다                 (rec)
    4. 시군구를 상가 기준 표기로 맞춘다                    (resolve_region)
    5. 프랜차이즈 표시, 중복 제거, 최소 건수 검사 후 저장     (main)

사용: python3 scripts/prep_certs.py   (먼저 prep_sangga.py 를 돌려 sgg_known.json 을 만들 것)
새 소스를 추가하려면: load_* 함수를 하나 만들고 아래 SOURCES 목록에 등록하면 된다.

함수 목록:
    [읽기 도구]   read_csv, ymd
    [공통 형식]   rec
    [소스별]     load_mobum, load_good_price, load_baengnyeon, load_tour, load_hygiene, load_ansim,
                load_lx
    [지역 보정]   resolve_region
    [실행]       main
"""
import csv
import json
import os
import sys
from collections import Counter   # 값별 개수 세기 (프랜차이즈 판별, 중복 검사)

from normalize import (jibun_key, license_year, name_core, name_norm, norm_sido, norm_tel,
                       road_key, sgg_city, split_branch, split_sido, stable_id)

HERE = os.path.dirname(os.path.abspath(__file__))     # 이 스크립트가 있는 폴더 (scripts/)
RAW = os.path.join(HERE, "..", "data", "raw")          # 원본 파일 폴더
OUT_DIR = os.path.join(HERE, "..", "data", "processed")

# ① 인증 공통 표의 열 구성. 7종 모두 이 모양으로 바꾼다. 해당 소스에 없는 정보는 빈칸.
COLS = [
    "cert_id",      # 고유번호. 소스 약자 + 원본 ID (예: 'MB-3000000-101-1999-10390')
    "source",       # 어느 인증인지 ('모범음식점' 등)
    "name_raw",     # 원래 이름 그대로 (화면 표시·라벨링용)
    "name_norm",    # 비교용 이름 (normalize.name_norm)
    "name_core",    # 지점명까지 뗀 본이름 (normalize.name_core)
    "branch",       # 떼어낸 지점명
    "sido",         # 시도 (정답 표기)
    "sgg_city",     # 시군구 첫 단어 ('고양시')
    "sgg_ok",       # 시군구가 상가의 시군구 목록에 있으면 '1'
    "addr_raw",     # 원래 주소 그대로
    "road_key",     # 건물 키 (도로명 기준) '시도|도로명|본번-부번'
    "jibun_key",    # 건물 키 (지번 기준)   '시도|법정동|번지'
    "tel",          # 전화번호 숫자만
    "food_raw",     # 원본의 업종·음식 유형 그대로
    "menu",         # 메뉴 정보 (착한가격 메뉴·가격, 모범음식점 주된음식종류, LX 대표메뉴)
    "cert_date",    # 인증 지정일 'YYYY-MM-DD'
    "valid_to",     # 인증 만료일 (식품안심업소만)
    "license_no",   # 인허가번호 (모범음식점·식품안심업소, 인증끼리 잇는 열쇠)
    "since_year",   # 인허가 연도 (오래된 가게 판단용)
    "lat", "lon",   # 좌표 (관광공사만)
    "is_chain",     # 같은 소스 안에 같은 본이름이 5곳 이상이면 '1' (프랜차이즈 추정)
]

# 유효기간 비교 기준일. 실행할 때마다 결과가 달라지지 않도록 날짜를 고정해 둔다.
TODAY = "2026-10-27"


# ════════════════════════════════════════════════════════════════════
# [읽기 도구]
# ════════════════════════════════════════════════════════════════════

def read_csv(name, enc):
    """data/raw 의 CSV 하나를 읽어 '열이름 → 값' 사전들의 목록으로 돌려준다.

    enc = 인코딩. 원본마다 다르다 (모범음식점·백년가게는 'cp949', 나머지는 'utf-8').
    인코딩을 틀리게 주면 한글이 깨지거나 읽다가 에러가 난다.
    """
    with open(os.path.join(RAW, name), encoding=enc) as f:
        return list(csv.DictReader(f))


def ymd(s):
    """날짜 표기를 'YYYY-MM-DD'로 통일한다. 날짜가 아니면 ''.

    소스마다 날짜 모양이 다르다: 식품안심 '20250128', 모범 '2025-01-28', 안심식당 빈값 'null'.
    숫자만 뽑아서 8자리 이상이면 앞 8자리로 날짜를 만든다.
    """
    d = "".join(ch for ch in (s or "") if ch.isdigit())
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else ""


# ════════════════════════════════════════════════════════════════════
# [공통 형식]
# ════════════════════════════════════════════════════════════════════

def rec(source, cert_id, name, addr, sido="", sgg="", jibun_addr="", **kw):
    """인증 한 건을 공통 형식(COLS) 한 행으로 만든다. 모든 load_* 함수가 이걸 쓴다.

    입력:
        source, cert_id, name, addr : 모든 소스에 있는 기본 정보
        sido, sgg   : 시도·시군구가 별도 열로 있는 소스만 넘긴다. 없으면 주소에서 뽑는다.
        jibun_addr  : 지번주소가 따로 있는 소스(모범음식점)만 넘긴다.
        **kw        : 그 밖의 열 (tel, food_raw, menu …). 이름=값 으로 넘기면 그대로 채운다.

    하는 일:
        1. 주소 앞머리에서 시도를 떼고, 별도 시도 열이 있으면 그걸 우선한다
        2. 시군구가 없으면 시도 바로 뒤 단어를 시군구로 본다 (세종은 시군구가 없어 시도 이름을 쓴다)
        3. 건물 키 두 개(road_key, jibun_key)를 만든다
        4. 이름을 비교용으로 정리하고 지점명을 떼어 둔다
    """
    a_sido, rest = split_sido(addr)             # 주소에서 뽑은 시도와 나머지
    sido = norm_sido(sido) or a_sido            # 별도 열 값이 있으면 그걸, 없으면 주소에서 뽑은 것
    if not sgg:
        sgg = rest.split()[0] if rest.split() else ""
    if sido == "세종특별자치시":                  # 세종은 시군구 단계가 없다
        sgg = "세종특별자치시"
    body = addr[len(addr) - len(rest):] if a_sido else addr   # 시도를 뗀 주소
    # 관광공사 주소 중 '중앙번영로 (6)'처럼 건물번호를 괄호에 넣은 것이 있다.
    # 괄호를 지우는 기본 처리로 못 찾으면 괄호 기호만 빼고 한 번 더 시도한다.
    rk = road_key(sido, body) or road_key(sido, body.replace("(", " ").replace(")", " "))
    _, branch = split_branch(name)
    r = dict.fromkeys(COLS, "")                 # 모든 열을 빈칸으로 시작
    r.update(cert_id=cert_id, source=source, name_raw=name.strip(),
             name_norm=name_norm(name), name_core=name_core(name), branch=branch,
             sido=sido, sgg_city=sgg_city(sgg), addr_raw=addr.strip(), road_key=rk,
             jibun_key=jibun_key(sido, jibun_addr or body))
    r.update(kw)                                # 소스별 추가 열 채우기
    return r


# ════════════════════════════════════════════════════════════════════
# [소스별] 원본 읽기 + 유효한 인증만 거르기 + 공통 형식으로 바꾸기
#   함수 하나가 소스 하나를 맡는다. 각 함수 설명에 "무엇을 거르는지"를 적었다.
# ════════════════════════════════════════════════════════════════════

def load_mobum():
    """모범음식점: 65,428행 중 지금 유효한 11,560건.

    거르기: 영업 중 AND (지정취소 없음 OR 취소 후 다시 지정됨)
            → 원본에 폐업·취소된 이력이 전부 남아 있어서 반드시 걸러야 한다.
    특이점: 도로명주소가 24% 비어 있어 지번주소('소재지주소')를 대신 쓴다.
            인허가번호 앞 4자리가 연도라 since_year 로 쓴다.
    """
    out = []
    for r in read_csv("모범음식점_20261021.csv", "cp949"):
        cancel = r["지정취소일자"]
        # 날짜가 'YYYY-MM-DD' 문자열이라 크기 비교(<=)가 곧 날짜 비교다
        if r["영업상태명"] != "영업" or (cancel and r["재지정일자"] <= cancel):
            continue                                       # 건너뛰기 (결과에 넣지 않음)
        lic = r["인허가번호"].strip()
        # 관리번호 '3000000-101-1999-10390'의 세 번째 조각도 연도다 (인허가번호가 이상할 때 대비)
        mgmt_year = r["관리번호"].split("-")[2] if r["관리번호"].count("-") >= 3 else ""
        out.append(rec(
            "모범음식점", "MB-" + r["관리번호"], r["업소명"],
            r["도로명주소"].strip() or r["소재지주소"].strip(), jibun_addr=r["소재지주소"],
            tel=norm_tel(r["전화번호"]), food_raw=r["음식의유형"], menu=r["주된음식종류"],
            cert_date=ymd(r["재지정일자"]) or ymd(r["지정일자"]), license_no=lic,
            since_year=license_year(lic) or (mgmt_year if mgmt_year.isdigit() else "")))
    return out


# 착한가격업소 '업종' 12종 중 음식점인 것
GOOD_PRICE_FOOD = {"한식", "중식", "일식", "양식", "기타요식업", "베이커리"}


def load_good_price():
    """착한가격업소: 12,935행 중 음식점 9,709건.

    거르기: 업종이 음식점 6종인 것만 (미용업·세탁업·숙박업 등 제외)
    특이점: 원본에 고유번호가 없어 이름+주소로 ID를 만든다(stable_id).
            메뉴1~4·가격1~4 를 '김치찌개 7000원 · 된장찌개 7000원' 한 줄로 합친다.
            원본에 같은 이름·주소 행이 1건 중복돼 있다(main 에서 하나만 남김).
    """
    out = []
    for r in read_csv("착한가격업소_20260930.csv", "utf-8-sig"):
        if r["업종"] not in GOOD_PRICE_FOOD:
            continue
        menu = " · ".join(f"{r[f'메뉴{i}'].strip()} {r[f'가격{i}'].strip()}원"
                          for i in range(1, 5) if r[f"메뉴{i}"].strip())
        out.append(rec("착한가격업소", "GP-" + stable_id(r["업소명"], r["주소"]),
                       r["업소명"], r["주소"], sido=r["시도"], sgg=r["시군"],
                       food_raw=r["업종"], menu=menu))
    return out


def load_baengnyeon():
    """백년가게: 1,511건 전부.

    거르기: 없음. 원본에 업종 열이 없어 식당인지 알 수 없다.
            → 상가와 매칭한 뒤 상가 업종으로 판별한다.
    특이점: 열이 4개뿐. 시도를 '서울', '전북'처럼 약칭으로 적는다(split_sido 가 처리).
            '연번'은 단순 행 번호라 ID로 쓰지 않고 이름+주소로 만든다.
    """
    return [rec("백년가게", "BN-" + stable_id(r["업체명"], r["업체주소"]),
                r["업체명"], r["업체주소"], tel=norm_tel(r["연락처"]))
            for r in read_csv("백년가게_20260820.csv", "cp949")]


# 관광공사 분류 코드 → 이름. API '분류체계 코드조회'에서 받은 정식 목록.
TOUR_CAT = {
    "FD010100": "관광식당", "FD010200": "모범음식점", "FD020100": "중식", "FD020200": "일식",
    "FD020300": "서양식", "FD020400": "기타외국식", "FD020500": "퓨전음식",
    "FD030100": "제과", "FD030200": "피자·햄버거·샌드위치", "FD030300": "치킨",
    "FD030400": "김밥 분식", "FD030500": "이동음식", "FD030600": "기타간이음식",
    "FD040100": "바/펍", "FD040200": "생맥주전문점", "FD040300": "클럽",
    "FD040400": "전통주/민속주점", "FD040500": "기타주점",
    "FD050100": "카페", "FD050200": "찻집", "FD050300": "기타음료점",
}


def load_tour():
    """관광공사 맛집: 13,408건 전부.

    거르기: 없음. 카페(3,044건)·주점도 남긴다 — 지도에 보여줄지는 나중에 정한다.
    특이점: 원본이 JSON. 6종 중 유일하게 좌표(mapx=경도, mapy=위도)가 있다.
            전화번호 열은 있지만 전부 비어 있다.
    """
    with open(os.path.join(RAW, "관광공사_음식점_20261022.json"), encoding="utf-8") as f:
        items = json.load(f)
    return [rec("관광공사", "TR-" + r["contentid"], r["title"],
                f"{r['addr1']} {r['addr2']}".strip(), tel=norm_tel(r["tel"]),
                food_raw=TOUR_CAT.get(r["lclsSystm3"], r["lclsSystm3"]),
                lat=r["mapy"], lon=r["mapx"])
            for r in items]


# 회사·학교 급식. 일반인이 찾아갈 식당이 아니라서 뺀다.
HG_NOT_PUBLIC = {"위탁급식영업", "집단급식소"}


def load_hygiene():
    """식품안심업소: 46,896행 중 44,977건.

    거르기: 정상 영업 AND 지정취소 없음 AND 유효기간(ASGN_TO)이 안 지남 AND 급식업 아님
            → 6종 중 유일하게 인증에 만료일이 있다. 안 거르면 만료된 인증이 지도에 뜬다.
    특이점: 프랜차이즈가 약 44% (메가커피·스타벅스…). 지우지 않고 is_chain 으로 표시만 한다.
            인허가번호(LCNS_NO)가 모범음식점과 같은 체계라 두 인증을 잇는 열쇠가 된다.
    """
    out = []
    today = TODAY.replace("-", "")          # 원본 날짜가 '20261027' 모양이라 맞춰서 비교
    for r in read_csv("식품안심업소_20261026.csv", "utf-8"):
        if (r["CLSBIZ_DVS_CD_NM"] != "정상" or r["ASGN_CANCEL_YMD"]
                or (r["ASGN_TO"] and r["ASGN_TO"] < today) or r["INDUTY_NM"] in HG_NOT_PUBLIC):
            continue
        out.append(rec("식품안심업소", "HG-" + r["HG_ASGN_NO"], r["BSSH_NM"], r["ADDR"],
                       food_raw=r["INDUTY_NM"], cert_date=ymd(r["HG_ASGN_YMD"]),
                       valid_to=ymd(r["ASGN_TO"]), license_no=r["LCNS_NO"],
                       since_year=license_year(r["LCNS_NO"])))
    return out


def load_ansim():
    """안심식당: 대전 990행 중 744건 (전국 데이터는 아직 없음).

    거르기: 선정여부가 'Y' AND 취소일이 없음
    특이점: 취소일이 비어 있을 때 빈칸이 아니라 'null'이라는 글자가 들어 있다.
            주소가 주소1(도로명)·주소2(상세)로 나뉘어 있어 주소1만 쓴다.
    """
    out = []
    for r in read_csv("안심식당_대전만_20261027.csv", "utf-8"):
        if r["선정여부"] != "Y" or r["안심식당취소일"].strip() not in ("", "null"):
            continue
        out.append(rec("안심식당", "AS-" + r["안심식당SEQ"], r["사업장명"], r["주소1"],
                       sido=r["시도명"], sgg=r["시군구명"], tel=norm_tel(r["전화번호"]),
                       food_raw=r["업종상세"], cert_date=ymd(r["안심식당지정일"])))
    return out


# LX 원본 주소의 오타·옛 행정구역. 고치지 않으면 시도가 틀려 건물 키가 상가와 안 맞는다.
LX_ADDR_FIX = {
    "대전과역시": "대전광역시",                       # 오타. split_sido 가 '과역시'를 시군구로 착각한다
    "전라남도 광영시": "전라남도 광양시",              # 오타
    "경상북도 문경읍": "경상북도 문경시 문경읍",        # 시 이름 빠짐
    "충청북도 청원군": "충청북도 청주시 청원구",        # 2014 청주시로 통합
    "경상북도 군위군": "대구광역시 군위군",            # 2023 대구로 편입 (시도가 바뀜)
    "경북 군위군": "대구광역시 군위군",
}


def load_lx():
    """LX 공사맛집: 2,013건 전부. 결정 일지 10번.

    정부 인증이 아니라 LX 직원들이 추천한 집이다. '맛집' 검색에서 가장 먼저 보여줄 근거로 쓴다.
    거르기: 없음. 카페(196건)도 남긴다 — 관광공사와 같은 이유.
    특이점: '등록번호'가 1~2013 단순 행 번호라 다음 판에서 바뀔 수 있다 → 이름+주소로 ID (백년가게와 같음).
            시도를 '경기'·'제주도'처럼 섞어 적는다(split_sido 가 처리). 전화번호 열은 없다.
            영업시간·주차정보·제안수·댓글수는 거의 다 비어 있어(2~8건) 쓰지 않는다.
    """
    out = []
    for r in read_csv("LX공사맛집_20260310.csv", "cp949"):
        addr = r["주소"].strip()
        for bad, good in LX_ADDR_FIX.items():
            addr = addr.replace(bad, good)
        out.append(rec("LX공사맛집", "LX-" + stable_id(r["상호"], addr), r["상호"], addr,
                       food_raw=r["업종"].strip(), menu=r["메뉴"].strip()))
    return out


# 실행할 소스 목록: (이름, 읽는 함수, 최소 건수)
# 최소 건수보다 적게 나오면 원본이 잘못 받아진 것으로 보고 저장하지 않고 멈춘다.
# (예: 다운로드가 중간에 끊겨 반만 받아졌는데 모르고 넘어가는 사고를 막는다)
SOURCES = [
    ("모범음식점", load_mobum, 10_000),
    ("착한가격업소", load_good_price, 8_000),
    ("백년가게", load_baengnyeon, 1_000),
    ("관광공사", load_tour, 12_000),
    ("식품안심업소", load_hygiene, 40_000),
    ("안심식당", load_ansim, 500),
    ("LX공사맛집", load_lx, 1_800),
]
CHAIN_MIN = 5   # 같은 본이름이 이 개수 이상이면 프랜차이즈로 표시


# ════════════════════════════════════════════════════════════════════
# [지역 보정]
# ════════════════════════════════════════════════════════════════════

def resolve_region(r, known, city_to_sido):
    """인증 한 행의 시도·시군구를 상가의 시군구 목록에 맞춘다. (r 을 직접 고친다)

    입력:
        r            : rec 가 만든 한 행
        known        : 시도별 시군구 목록 (상가 기준, sgg_known.json)
        city_to_sido : 시군구 → 그 시군구가 있는 시도들 (known 을 거꾸로 뒤집은 것)

    처리하는 경우:
        '원주'              → '원주시'        (끝의 시·군·구를 빠뜨린 약칭)
        '청주시 상당구 …'    → 시도 '충청북도' 보충  (주소에 시도가 아예 없음. 전국에 청주시가 하나뿐이라 확정 가능)
        인천 옛 '중구'       → 못 맞춤, sgg_ok 비움 (2026 구 개편으로 이름이 사라짐)
    """
    sgg = r["sgg_city"]
    # 시도가 비어 있고, 이 시군구 이름이 전국에 딱 한 시도에만 있으면 그 시도로 채운다
    if not r["sido"] and len(city_to_sido.get(sgg, ())) == 1:
        r["sido"] = next(iter(city_to_sido[sgg]))
        r["road_key"] = road_key(r["sido"], r["addr_raw"])    # 시도가 생겼으니 건물 키 다시 만들기
        r["jibun_key"] = jibun_key(r["sido"], r["addr_raw"])
    cities = known.get(r["sido"], set())
    if sgg not in cities:
        # '원주' + '시' 처럼 끝 글자를 붙여서 목록에 있으면 그걸로
        sgg = next((sgg + suf for suf in ("시", "군", "구") if sgg + suf in cities), sgg)
    r["sgg_city"], r["sgg_ok"] = sgg, "1" if sgg in cities else ""


# ════════════════════════════════════════════════════════════════════
# [실행]
# ════════════════════════════════════════════════════════════════════

def main():
    """전체 실행: 소스별로 읽기 → 검사 → 보정 → 합쳐서 저장 → 요약 출력."""
    # 상가 기준 시군구 목록 불러오기 (prep_sangga.py 가 만든 파일)
    with open(os.path.join(OUT_DIR, "sgg_known.json"), encoding="utf-8") as f:
        known = {s: {sgg_city(x) for x in v} for s, v in json.load(f).items()}
    city_to_sido = {}
    for s, cities in known.items():
        for c in cities:
            city_to_sido.setdefault(c, set()).add(s)

    rows, report = [], []
    for name, loader, min_rows in SOURCES:
        recs = loader()                       # 소스 하나 읽기
        if len(recs) < min_rows:
            sys.exit(f"{name} {len(recs):,}건 — 최소 {min_rows:,}건 미달, 원본을 확인할 것")

        # 프랜차이즈 표시: 같은 소스 안에서 본이름별 개수를 세서 5곳 이상이면 '1' (지우지는 않음)
        cnt = Counter(r["name_core"] for r in recs)
        for r in recs:
            r["is_chain"] = "1" if cnt[r["name_core"]] >= CHAIN_MIN else ""
            resolve_region(r, known, city_to_sido)

        # 중복 제거: 원본에 완전히 같은 행이 두 번 실려 ID가 겹치면 첫 번째만 남긴다
        ids = Counter(r["cert_id"] for r in recs)
        dup = sum(v - 1 for v in ids.values() if v > 1)
        if dup:
            seen, uniq = set(), []
            for r in recs:
                if r["cert_id"] not in seen:
                    seen.add(r["cert_id"])
                    uniq.append(r)
            recs = uniq
        rows += recs

        # 요약용 숫자: 시도·시군구·건물 키가 채워진 비율, 프랜차이즈 수
        n = len(recs)
        report.append((name, n, dup,
                       sum(bool(r["sido"]) for r in recs) / n,
                       sum(r["sgg_ok"] == "1" for r in recs) / n,
                       sum(bool(r["road_key"]) for r in recs) / n,
                       sum(bool(r["road_key"] or r["jibun_key"]) for r in recs) / n,
                       sum(r["is_chain"] == "1" for r in recs)))

    # 7종을 한 파일로 저장
    out = os.path.join(OUT_DIR, "certs.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)

    print(f"인증 {len(rows):,}건 → {os.path.normpath(out)}\n")
    print(f"{'소스':<8}{'건수':>8}{'중복제거':>8}{'시도':>8}{'시군구':>8}{'건물키':>8}{'건물|지번':>10}{'체인':>8}")
    for name, n, dup, sd, sg, rk, anyk, ch in report:
        print(f"{name:<8}{n:>8,}{dup:>8,}{sd:>8.1%}{sg:>8.1%}{rk:>8.1%}{anyk:>10.1%}{ch:>8,}")


if __name__ == "__main__":
    main()

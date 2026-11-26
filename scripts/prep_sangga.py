"""상가(상권)정보 277만 → data/processed/sangga.csv (② 상가 정제 표)

하는 일:
    1. 시도별 CSV 16개를 차례로 읽는다
    2. 한 행씩 필요한 열만 골라 비교하기 좋은 모양으로 바꾼다   (row)
    3. 한 파일로 저장하고, 시도별 시군구 목록도 따로 저장한다    (main)

사용: python3 scripts/prep_sangga.py   (약 30초)
결과:
    data/processed/sangga.csv       상가 정제 표 (약 800MB)
    data/processed/sgg_known.json   시도별 시군구 목록 → prep_certs.py 가 인증 쪽 시군구를 맞출 때 쓴다

업종으로 거르지 않는 이유:
    인증 '한우촌'(식당)과 상가 '한우촌판매장'(정육점)처럼, 같은 건물의 비식당이 헷갈리는 후보로 나온다.
    비식당을 미리 지우면 "식당이 아니라서 다른 가게"라고 판단할 기회 자체가 사라진다.

함수 목록:
    row   상가 원본 한 행 → 정제 표 한 행
    main  전체 실행
"""
import csv
import glob
import json
import os
import sys
from collections import Counter, defaultdict

from normalize import jibun_key, name_core, name_norm, sgg_city

SANGGA_DIR = "/Users/kimjihwan/Downloads/맛집 프로젝트 공공데이터/소상공인시장진흥공단_상가(상권)정보_20260630"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "processed")
MIN_ROWS = 2_500_000   # 이보다 적으면 원본 일부가 빠진 것으로 보고 멈춘다

# ② 상가 정제 표의 열 구성 (원본 39열 중 매칭·표시에 필요한 것만)
COLS = [
    "store_id",        # 상가업소번호 = 이 프로젝트의 가게 ID
    "name_raw",        # 상호명 그대로
    "branch_raw",      # 지점명 그대로 (13%만 채워짐)
    "name_norm",       # 상호명 비교용 (normalize.name_norm)
    "name_core",       # 상호명에서 지점까지 뗀 본이름
    "name_full_norm",  # 상호명 + 지점명 합친 비교용 ('곽만근갈비탕평내점') ← 인증은 둘을 붙여 적으니까
    "cat_large", "cat_mid", "cat_small",   # 업종 대·중·소분류 (소분류 246종)
    "sido", "sgg",     # 시도, 시군구 그대로 ('고양시 덕양구')
    "sgg_city",        # 시군구 첫 단어 ('고양시')
    "road_key",        # 건물 키 (도로명 기준) — 인증 쪽과 같은 모양
    "jibun_key",       # 건물 키 (지번 기준)
    "bldg_name",       # 건물명 (32%만 채워짐)
    "floor",           # 층 (55%만 채워짐)
    "lon", "lat",      # 경도, 위도
]


def row(r):
    """상가 원본 한 행(열이름 → 값 사전)을 정제 표 한 행으로 바꾼다.

    건물 키를 만드는 방법이 인증 쪽과 다르다:
        인증은 주소 문자열을 parse_road 로 쪼개야 하지만,
        상가는 '도로명', '건물본번지', '건물부번지'가 **이미 따로 열로 있다**. 그걸 그대로 조립한다.
        (문자열 파싱보다 정확하다)
        단 '도로명' 열은 '대전광역시 동구 은어송로'처럼 앞에 시도·시군구가 붙어 있어 마지막 단어만 쓴다.
    결과 모양은 인증 쪽 road_key 와 똑같이 '시도|도로명|본번-부번' 이 되도록 맞췄다.
    """
    sido = r["시도명"]
    road = r["도로명"].split()[-1] if r["도로명"].strip() else ""   # '… 은어송로' → '은어송로'
    main = r["건물본번지"].strip()
    # 부번지가 비어 있으면 0. int() 로 '007' 같은 앞자리 0 제거
    rkey = f"{sido}|{road}|{int(main)}-{int(r['건물부번지'] or 0)}" if road and main.isdigit() else ""
    full = r["상호명"] + (" " + r["지점명"] if r["지점명"] else "")
    return {
        "store_id": r["상가업소번호"],
        "name_raw": r["상호명"], "branch_raw": r["지점명"],
        "name_norm": name_norm(r["상호명"]), "name_core": name_core(r["상호명"]),
        "name_full_norm": name_norm(full),
        "cat_large": r["상권업종대분류명"], "cat_mid": r["상권업종중분류명"],
        "cat_small": r["상권업종소분류명"],
        "sido": sido, "sgg": r["시군구명"], "sgg_city": sgg_city(r["시군구명"]),
        "road_key": rkey, "jibun_key": jibun_key(sido, r["지번주소"]),
        "bldg_name": r["건물명"], "floor": r["층정보"],
        "lon": r["경도"], "lat": r["위도"],
    }


def main():
    """시도 파일 16개를 읽어 정제 표 하나로 저장하고, 요약 숫자를 출력한다.

    277만 행을 한꺼번에 메모리에 올리지 않고 한 행 읽을 때마다 바로 써서 메모리를 아낀다.
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    paths = sorted(glob.glob(f"{SANGGA_DIR}/*.csv"))
    if len(paths) != 16:   # 시도 파일이 빠졌으면 전국 데이터가 아니므로 멈춘다
        sys.exit(f"상가 시도 파일이 16개가 아니다: {len(paths)}개")
    sgg_known = defaultdict(set)   # 시도 → 그 시도에 나온 시군구들
    c = Counter()                  # 요약용 개수 세기
    out = os.path.join(OUT_DIR, "sangga.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        for p in paths:
            with open(p, encoding="utf-8") as src:
                for r in csv.DictReader(src):
                    o = row(r)
                    w.writerow(o)
                    sgg_known[o["sido"]].add(o["sgg"])
                    c["rows"] += 1
                    c["road"] += bool(o["road_key"])
                    c["jibun"] += bool(o["jibun_key"])
                    c["food"] += o["cat_large"] == "음식"
            # 진행 상황 (파일 이름에서 '서울' 같은 시도 부분만 출력)
            print(f"  {os.path.basename(p).split('_')[-2]:<6} 누적 {c['rows']:,}", file=sys.stderr)
    if c["rows"] < MIN_ROWS:
        sys.exit(f"상가 {c['rows']:,}행 — 최소 {MIN_ROWS:,}행 미달")
    with open(os.path.join(OUT_DIR, "sgg_known.json"), "w", encoding="utf-8") as f:
        json.dump({k: sorted(v) for k, v in sgg_known.items()}, f, ensure_ascii=False, indent=1)

    n = c["rows"]
    print(f"상가 {n:,}행 → {os.path.normpath(out)}")
    print(f"  건물 키 {c['road'] / n:.1%} · 지번 키 {c['jibun'] / n:.1%} · 음식점 {c['food']:,}")


if __name__ == "__main__":
    main()

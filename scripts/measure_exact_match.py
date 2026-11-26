"""인증 데이터 ↔ 상가(상권)정보 상호명 완전일치 매칭률 측정.

사용: python3 scripts/measure_exact_match.py {good_price|mobum}
판정 기준(숫자 보기 전에 확정):
  착한가격업소 — 80%+ 설계 변경 / 30~60% 성립 / 30% 미만 아주 좋음
  모범음식점   — 70%+ 이면 매칭은 파이프라인 한 단계로 내리고 핵심 기술을 검색·지도로 옮긴다
못 찾은 건은 같은 건물 주소에 상가가 있는지로 "표기 차이"와 "상가에 없음"을 가른다.
"""
import csv
import glob
import os
import random
import re
import sys
from collections import Counter, defaultdict

SANGGA_DIR = "/Users/kimjihwan/Downloads/맛집 프로젝트 공공데이터/소상공인시장진흥공단_상가(상권)정보_20260630"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw")
GOOD_PRICE = os.path.join(RAW, "착한가격업소_20260930.csv")
MOBUM = os.path.join(RAW, "모범음식점_20261021.csv")
FOOD_TYPES = {"한식", "중식", "일식", "양식", "기타요식업", "베이커리"}


def load_good_price():
    """음식점 업종만. → [(업소명, 시도, 시군구, 주소)]"""
    with open(GOOD_PRICE, encoding="utf-8-sig") as f:
        return [(r["업소명"], r["시도"], r["시군"], r["주소"])
                for r in csv.DictReader(f) if r["업종"] in FOOD_TYPES]


def load_mobum():
    """영업 중이고 지정이 유지된 것만 (취소 후 재지정은 유지로 본다)."""
    out = []
    with open(MOBUM, encoding="cp949") as f:
        for r in csv.DictReader(f):
            cancel = r["지정취소일자"]
            if r["영업상태명"] != "영업" or (cancel and r["재지정일자"] <= cancel):
                continue
            addr = r["도로명주소"].strip() or r["소재지주소"].strip()
            parts = addr.split()
            out.append((r["업소명"], parts[0], parts[1] if len(parts) > 1 else "", addr))
    return out


SOURCES = {
    "good_price": ("착한가격업소 음식점", load_good_price),
    "mobum": ("모범음식점 (영업·지정유지)", load_mobum),
}

# "동일로 1353", "대저로221번다길 43-1" → (도로명, 건물번호)
ROAD_RE = re.compile(r"(\S+?(?:로|길))\s*(\d+(?:-\d+)?)(?=\s|,|\(|$)")


def road_key(sido, sgg, addr):
    m = ROAD_RE.search(addr)
    if not m:
        return None
    return (sido, sgg.split()[0] if sgg else "", m.group(1), m.group(2))


def norm(name):
    """공백·괄호내용·특수문자 제거 (완전일치 대비 참고용)."""
    name = re.sub(r"\(.*?\)|\[.*?\]", "", name)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", name).lower()


def load_sangga():
    names_all = set()
    names_sgg = set()
    by_addr = defaultdict(list)
    sidos = Counter()
    n = 0
    for path in sorted(glob.glob(f"{SANGGA_DIR}/*.csv")):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                n += 1
                sido, sgg = r["시도명"], r["시군구명"].split()[0]
                sidos[sido] += 1
                full = r["상호명"] + (" " + r["지점명"] if r["지점명"] else "")
                for nm in {r["상호명"], full}:
                    names_all.add(nm)
                    names_sgg.add((sido, sgg, nm))
                k = road_key(sido, sgg, r["도로명주소"].replace(r["시도명"], "", 1))
                if k:
                    by_addr[k].append((r["상호명"], full, r["상권업종대분류명"]))
        print(f"  {path.rsplit('_', 2)[-2]} 누적 {n:,}", file=sys.stderr)
    return n, names_all, names_sgg, by_addr, sidos


def pct(a, b):
    return f"{a:,}/{b:,} = {a / b * 100:.1f}%"


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SOURCES:
        sys.exit(f"사용: {sys.argv[0]} {{{'|'.join(SOURCES)}}}")
    label, loader = SOURCES[sys.argv[1]]
    rows = loader()
    total = len(rows)

    random.seed(0)
    print("상가 로딩...", file=sys.stderr)
    n, names_all, names_sgg, by_addr, sidos = load_sangga()
    print(f"상가 {n:,}건, 도로명 주소키 {len(by_addr):,}개\n")

    missing_sido = {r[1] for r in rows} - set(sidos)
    if missing_sido:
        sys.exit(f"시도명 불일치: {missing_sido}")

    c = Counter()
    buckets = defaultdict(list)
    for raw_name, sido, raw_sgg, addr in rows:
        sgg, name = raw_sgg.split()[0] if raw_sgg else "", raw_name.strip()
        k = road_key(sido, sgg, addr.replace(sido, "", 1))
        at_addr = by_addr.get(k, []) if k else []
        exact_nat = name in names_all
        exact_sgg = (sido, sgg, name) in names_sgg
        exact_addr = any(name in (a, b) for a, b, _ in at_addr)
        norm_addr = any(norm(name) in (norm(a), norm(b)) for a, b, _ in at_addr)
        c["nat"] += exact_nat
        c["sgg"] += exact_sgg
        c["addr"] += exact_addr
        c["norm_addr"] += norm_addr
        c["no_key"] += k is None

        if exact_sgg:
            continue
        # 시군구 완전일치 실패분 분류
        food_at = [x for x in at_addr if x[2] == "음식"]
        if k is None:
            b = "주소 파싱 실패"
        elif not at_addr:
            b = "같은 건물에 상가 없음"
        elif food_at:
            b = "같은 건물에 식당 있음 (표기 차이 후보)"
        else:
            b = "같은 건물에 비식당만 있음"
        buckets[b].append((name, addr, [x[1] for x in (food_at or at_addr)][:4]))

    print(f"[{label} {total:,}건]\n")
    print("■ 완전일치 매칭률")
    print(f"  전국 아무 데나 같은 상호      {pct(c['nat'], total)}   (동명이인 포함, 과대추정)")
    print(f"  같은 시군구 + 같은 상호       {pct(c['sgg'], total)}   ← 기준 수치")
    print(f"  같은 건물 + 같은 상호         {pct(c['addr'], total)}")
    print(f"  같은 건물 + 정규화 상호       {pct(c['norm_addr'], total)}   (공백·괄호·특수문자 제거)")
    print(f"  (주소 파싱 실패 {c['no_key']:,}건)\n")

    miss = total - c["sgg"]
    print(f"■ 시군구 완전일치 실패 {miss:,}건 분류")
    for b, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
        print(f"  {b:<28} {pct(len(items), miss)}")
    print()
    for b, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
        print(f"── {b} 샘플")
        for name, addr, cands in random.sample(items, min(12, len(items))):
            print(f"  {name}  |  {addr}")
            if cands:
                print(f"      → 상가: {cands}")
        print()


if __name__ == "__main__":
    main()

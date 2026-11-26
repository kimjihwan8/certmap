"""농림축산식품부 안심식당 전량 수집 → data/raw/안심식당.json

사용: MAFRA_KEY=... python3 scripts/fetch_ansim.py
필드 함정(참고 레포 실측): RELAX_SI_NM=시도, RELAX_SIDO_NM=시군구 (이름과 반대).
대표자 실명(RELAX_RSTRNT_REPRESENT)은 개인정보라 저장하지 않는다.
"""
import json
import os
import sys
import time
import urllib.request

SVC = "Grid_20200713000000000605_1"
BASE = f"http://211.237.50.150:7080/openapi/{os.environ['MAFRA_KEY']}/json/{SVC}"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw", "안심식당.json")
DROP = {"RELAX_RSTRNT_REPRESENT"}


def fetch(start, end):
    with urllib.request.urlopen(f"{BASE}/{start}/{end}", timeout=60) as r:
        body = json.loads(r.read().decode("utf-8-sig"))
    if SVC not in body:
        sys.exit(f"API 오류: {body}")
    return body[SVC]


def main():
    total = int(fetch(1, 1)["totalCnt"])
    rows = []
    for start in range(1, total + 1, 1000):
        rows += fetch(start, min(start + 999, total)).get("row") or []
        print(f"  {len(rows):,}/{total:,}", file=sys.stderr)
        time.sleep(0.15)
    if len(rows) != total:
        sys.exit(f"수집 건수 불일치: {len(rows)} != {total}")
    rows = [{k: v for k, v in r.items() if k not in DROP} for r in rows]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    print(f"{total:,}건 저장 → {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()

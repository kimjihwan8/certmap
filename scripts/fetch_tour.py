"""한국관광공사 국문관광정보(KorService2) 음식점 목록 전량 수집 → data/raw/관광공사_음식점_YYYYMMDD.json

사용: DATA_GO_KR_KEY=... python3 scripts/fetch_tour.py
개발계정은 하루 1,000콜. 목록은 1,000건씩이라 약 14콜이면 전량이다.
대표메뉴·영업시간(소개정보조회)은 업소당 1콜이라 여기서 받지 않는다.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

URL = "https://apis.data.go.kr/B551011/KorService2/areaBasedList2"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw")
ROWS = 1000


def fetch(page):
    q = urllib.parse.urlencode({
        "serviceKey": os.environ["DATA_GO_KR_KEY"], "MobileOS": "ETC", "MobileApp": "certmap",
        "_type": "json", "numOfRows": ROWS, "pageNo": page,
        "contentTypeId": 39, "arrange": "A",  # 39 = 음식점
    })
    with urllib.request.urlopen(f"{URL}?{q}", timeout=60) as r:
        body = json.load(r)
    if "response" not in body or body["response"]["header"]["resultCode"] != "0000":
        sys.exit(f"API 오류: {body}")
    return body["response"]["body"]


def main():
    items, page = [], 1
    while True:
        b = fetch(page)
        got = (b.get("items") or {}).get("item") or []
        items += [got] if isinstance(got, dict) else got
        total = int(b["totalCount"])
        print(f"  {len(items):,}/{total:,}", file=sys.stderr)
        if len(items) >= total or not got:
            break
        page += 1
        time.sleep(0.2)
    if len(items) != total:
        sys.exit(f"수집 건수 불일치: {len(items)} != {total}")
    out = os.path.join(RAW, f"관광공사_음식점_{time.strftime('%Y%m%d')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    print(f"{total:,}건 저장 ({page}콜) → {os.path.normpath(out)}")


if __name__ == "__main__":
    main()

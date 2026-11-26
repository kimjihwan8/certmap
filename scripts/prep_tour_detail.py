"""관광공사 상세 기록장(jsonl) → data/processed/tour_detail.csv. 결정 일지 24·33번.

사용: python3 scripts/prep_tour_detail.py   (fetch_tour_detail.py 가 매일 받는 중이어도 언제든 돌릴 수 있다)

하는 일:
    1. 기록장을 읽어 가게마다 마지막 줄만 남긴다 (fetch_tour_detail.py 는 덧붙이기만 하므로 마지막 줄이 최신)
    2. 삭제 기록(관광공사가 숨긴 가게)은 뺀다
    3. 소개글의 HTML 꼬리표(<br> 등)와 &nbsp; 같은 기호를 글자로 바꾼다
    4. 인증 표의 관광공사 인증 번호('TR-' + contentid)로 잇는다 → DB 에서 가게(store_id)와 연결된다

결과 열:
    cert_id     'TR-' + contentid (certs.csv 의 관광공사 인증 번호와 같다)
    overview    소개글 (의미 검색에 쓴다)
    first_menu  대표메뉴
    menus       취급메뉴
    parking     주차
    open_time   영업시간
    rest_day    휴무일
    license_no  인허가번호 (2단계 재매칭 후보, 결정 24번)
"""
import csv
import html
import json
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "data", "raw", "관광공사_상세.jsonl")
OUT = os.path.join(ROOT, "data", "processed", "tour_detail.csv")
COLS = ["cert_id", "overview", "first_menu", "menus", "parking", "open_time", "rest_day", "license_no"]


def clean(s):
    """HTML 꼬리표를 띄어쓰기로, 기호(&amp; 등)를 글자로, 여러 칸 띄어쓰기를 한 칸으로."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    latest = {}
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            latest[r["contentid"]] = r

    rows, deleted, empty = [], 0, 0
    for cid, r in latest.items():
        if r.get("deleted"):
            deleted += 1
            continue
        common, intro = r.get("common", {}), r.get("intro", {})
        overview = clean(common.get("overview"))
        if not overview:
            empty += 1
        rows.append({
            "cert_id": "TR-" + cid,
            "overview": overview,
            "first_menu": clean(intro.get("firstmenu")),
            "menus": clean(intro.get("treatmenu")),
            "parking": clean(intro.get("parkingfood")),
            "open_time": clean(intro.get("opentimefood")),
            "rest_day": clean(intro.get("restdatefood")),
            "license_no": clean(intro.get("lcnsno")),
        })

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"관광공사 상세 {len(rows):,}곳 → {os.path.normpath(OUT)}  (숨김 {deleted:,}곳 뺌, 소개글 없음 {empty:,}곳)")


if __name__ == "__main__":
    main()

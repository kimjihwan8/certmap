"""관광공사 음식점 상세(소개글·대표메뉴·주차·영업시간·인허가번호) 수집·동기화 → data/raw/관광공사_상세.jsonl. 결정 일지 24·26번.

사용: python3 scripts/fetch_tour_detail.py            (하루 한 번. 키는 환경변수 DATA_GO_KR_KEY 또는 .env)
      python3 scripts/fetch_tour_detail.py --dry-run  (오늘 할 일만 보기. 상세는 안 받음)

매일 같은 순서로 돈다 (처음 다 받기와 이후 갱신을 한 스크립트가 한다):
    1. 동기화 목록(areaBasedSyncList2)을 받는다
         showflag=1  지금 보이는 가게 + 마지막 수정 시각
         showflag=0  관광공사가 숨긴(삭제·비공개) 가게
    2. 숨긴 가게           → 삭제로 기록한다
    3. 수정 시각이 바뀐 가게 → 상세를 다시 받는다
    4. 아직 안 받은 가게     → 상세를 받는다 (대전 먼저)
       3·4 를 합쳐 하루 DAILY_BUDGET 곳까지. 개발 계정은 기능마다 하루 1,000번이다.
    처음 약 14일은 4번이 예산을 거의 다 쓰고, 다 받은 뒤에는 2·3번만 하루 수십 곳씩 돈다.

삭제를 "목록에서 사라졌다"로 추측하지 않는 이유:
    목록을 받다 API가 중간에 실패하면 멀쩡한 가게 수천 곳이 사라진 것처럼 보인다.
    그래서 관광공사가 직접 숨김 표시(showflag=0)한 가게만 삭제로 본다.
    목록 수가 API가 알려준 전체 수(totalCount)와 다르면 그날은 아무것도 판단하지 않고 멈춘다.

결과 파일 = 기록장. 한 줄씩 덧붙이기만 하고 고치지 않는다. 같은 가게는 가장 마지막 줄이 최신이다.
    상세:  {"contentid", "fetched": 받은 날, "version": 관광공사 수정 시각, "common": {...}, "intro": {...}}
    삭제:  {"contentid", "fetched": 기록한 날, "version": 숨김 처리 시각, "deleted": true}
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BASE = "https://apis.data.go.kr/B551011/KorService2/"
OUT = os.path.join(ROOT, "data", "raw", "관광공사_상세.jsonl")
DAILY_BUDGET = 950       # 기능별 하루 1,000번 중 950번만 쓴다 (시험 호출할 여유를 남김)
FIRST_SIDO = "대전"      # 아직 안 받은 가게 중 이 시도를 먼저 받는다
ROWS = 1000              # 목록 한 번에 받는 수


class QuotaExceeded(Exception):
    """하루 한도를 넘었다는 응답. 오늘은 그만 받는다."""


def api_key():
    """환경변수 → 없으면 프로젝트 루트의 .env 에서 DATA_GO_KR_KEY 를 읽는다 (매일 자동 실행할 때 편하도록)."""
    if os.environ.get("DATA_GO_KR_KEY"):
        return os.environ["DATA_GO_KR_KEY"]
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        with open(env, encoding="utf-8") as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k == "DATA_GO_KR_KEY":
                    return v
    sys.exit("DATA_GO_KR_KEY 가 없다 (환경변수 또는 .env)")


def call(endpoint, **params):
    """API 한 번 호출. 응답 body 를 돌려준다."""
    q = urllib.parse.urlencode({"serviceKey": api_key(), "MobileOS": "ETC", "MobileApp": "certmap",
                                "_type": "json", **params})
    try:
        with urllib.request.urlopen(f"{BASE}{endpoint}?{q}", timeout=60) as r:
            text = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 429:            # 한도 초과는 HTTP 429 로 온다 (2026-11-26 확인)
            raise QuotaExceeded(endpoint) from e
        raise
    # 예전 방식의 한도 초과 응답: _type=json 을 줘도 XML 글자로 온다
    if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in text:
        raise QuotaExceeded(endpoint)
    body = json.loads(text)
    header = body["response"]["header"]
    if header["resultCode"] != "0000":
        raise RuntimeError(f"{endpoint} 오류: {header}")
    return body["response"]["body"]


def first_item(body):
    items = (body.get("items") or {}).get("item") or [{}]
    return items[0] if isinstance(items, list) else items


def fetch_list(showflag):
    """동기화 목록 전체를 받는다. contentid → 목록 항목. 수가 totalCount 와 다르면 멈춘다."""
    out, page = {}, 1
    while True:
        b = call("areaBasedSyncList2", contentTypeId=39, showflag=showflag, numOfRows=ROWS, pageNo=page)
        got = (b.get("items") or {}).get("item") or []
        for it in [got] if isinstance(got, dict) else got:
            out[it["contentid"]] = it
        total = int(b["totalCount"])
        if len(out) >= total or not got:
            break
        page += 1
        time.sleep(0.2)
    if len(out) != total:
        sys.exit(f"목록이 덜 받아졌다 (showflag={showflag}: {len(out)} / {total}) — 오늘은 판단하지 않고 멈춘다")
    return out


def load_state():
    """기록장을 처음부터 읽어 가게마다 가장 마지막 줄만 남긴다."""
    state = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                state[r["contentid"]] = r
    return state


def version(rec):
    """기록의 관광공사 수정 시각. 처음 받은 줄들은 version 칸이 없어 상세 응답의 modifiedtime 을 쓴다."""
    return rec.get("version") or rec.get("common", {}).get("modifiedtime", "")


def main():
    today = time.strftime("%Y-%m-%d")
    visible = fetch_list(1)
    hidden = fetch_list(0)
    state = load_state()
    alive = {cid: r for cid, r in state.items() if not r.get("deleted")}

    # 2. 숨긴 가게 → 삭제 기록
    deleted = [cid for cid in alive if cid in hidden]
    # 3. 수정된 가게 → 다시 받기 (목록의 수정 시각이 우리 기록보다 늦다)
    modified = [cid for cid, r in alive.items() if cid in visible and visible[cid]["modifiedtime"] > version(r)]
    # 4. 아직 안 받은 가게. 대전 먼저 (sorted 는 False < True 라서 대전이 앞에 온다)
    todo = sorted((cid for cid in visible if cid not in alive),
                  key=lambda cid: not visible[cid]["addr1"].startswith(FIRST_SIDO))
    # 보이지도 숨겨지지도 않은 가게: 이유를 모르므로 판단하지 않고 세기만 한다
    unknown = sum(1 for cid in alive if cid not in visible and cid not in hidden)
    print(f"목록: 보임 {len(visible):,} / 숨김 {len(hidden):,}   기록: {len(alive):,}곳", file=sys.stderr)
    print(f"오늘 할 일: 삭제 {len(deleted):,} / 수정 {len(modified):,} / 안 받음 {len(todo):,}"
          + (f" / 판단 보류 {unknown:,}" if unknown else ""), file=sys.stderr)
    if "--dry-run" in sys.argv:          # 할 일만 보여주고 아무것도 받거나 기록하지 않는다
        return

    got = 0
    with open(OUT, "a", encoding="utf-8") as f:
        for cid in deleted:
            f.write(json.dumps({"contentid": cid, "fetched": today, "version": hidden[cid]["modifiedtime"],
                                "deleted": True}, ensure_ascii=False) + "\n")
        try:
            for cid in (modified + todo)[:DAILY_BUDGET]:
                common = first_item(call("detailCommon2", contentId=cid))
                intro = first_item(call("detailIntro2", contentId=cid, contentTypeId=39))
                f.write(json.dumps({"contentid": cid, "fetched": today, "version": visible[cid]["modifiedtime"],
                                    "common": common, "intro": intro}, ensure_ascii=False) + "\n")
                f.flush()            # 중간에 멈춰도 받은 줄은 파일에 남도록
                got += 1
                if got % 100 == 0:
                    print(f"  {got:,}", file=sys.stderr)
                time.sleep(0.1)
        except QuotaExceeded as e:
            print(f"하루 한도 초과 ({e}) — 내일 이어서 받는다", file=sys.stderr)

    left = len(modified) + len(todo) - got
    print(f"{today}: 삭제 기록 {len(deleted):,} / 상세 받음 {got:,} → 남음 {left:,}곳"
          + (f" (약 {-(-left // DAILY_BUDGET)}일)" if left else " — 최신 상태"))


if __name__ == "__main__":
    main()

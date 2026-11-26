"""2단계: 상가에서 못 찾은 인증에 가게 번호를 준다. 결정 일지 3·23·25번.

사용: python3 scripts/match_stage2.py        (match_all.py 다음에)

1단계(match_all.py)에서 상가에 붙지 못한 인증 약 2만 건을 처리한다:
    1. 물려받기  상가에 붙은 다른 인증과 같은 가게면 그 상가업소번호를 물려받는다
                 열쇠: 인허가번호 / 전화번호+같은 건물 / 같은 건물+같은 이름
                 이어지는 가게가 둘 이상이면 물려받지 않는다 (틀린 확정보다 보류 — v1과 같은 원칙)
    2. 묶기      남은 인증끼리 같은 가게를 묶는다. 같은 건물 안에서만 묶는다.
                 (건물을 넘어 묶으면 A=B, B=C → A=C 로 잘못 묶인 게 번진다. 결정 3번)
    3. 새 가게   묶음 하나 = 새 가게 하나. 번호는 'C-' + 묶음에서 가장 앞선 인증 번호
                 좌표: 같은 건물 상가 가게 좌표 → 원본 좌표(관광공사) → 지오코딩 결과(geocode.csv, 있으면)

결과:
    data/processed/cert_store.csv  인증 1건 = 1행, 모든 인증의 최종 가게 번호
        cert_id, store_id, stage ('1'=상가에 붙음, '2'=이 스크립트), how (판정 이유)
    data/processed/new_stores.csv  상가에 없는 새 가게
    results/match_stage2.txt       요약
"""
import csv
import os
import statistics
from collections import Counter, defaultdict

from match_core import ROOT, SAME_NAME, candidates, level, load_certs, load_index

PROCESSED = os.path.join(ROOT, "data", "processed")
GEOCODE = os.path.join(PROCESSED, "geocode.csv")   # 지오코딩 결과 (브이월드·카카오). 없으면 그 좌표는 빈칸

# 새 가게의 이름을 어느 인증에서 가져올지. 위에 있을수록 우선 — 공식 인증 원본의 상호를 먼저 쓴다.
NAME_PRIORITY = ["모범음식점", "백년가게", "착한가격업소", "안심식당", "식품안심업소", "관광공사", "LX공사맛집"]

NEW_COLS = ["store_id", "name", "branch", "name_norm", "food", "sido", "sgg", "road_key",
            "addr", "lat", "lon", "coord_source", "sources"]


def building(c):
    """인증의 건물 키. 도로명 키가 없으면 지번 키."""
    return c["road_key"] or c["jibun_key"]


def as_store(c):
    """인증 한 건을 level() 이 비교할 수 있는 '상가 가게' 모양으로 바꾼다 (인증끼리 이름 비교용)."""
    return {"name_norm": c["name_norm"], "name_core": c["name_core"],
            "name_full_norm": c["name_norm"], "branch_raw": c["branch"]}


def same_name(a, b):
    return level(a, as_store(b)) in SAME_NAME


def linked(a, b):
    """두 인증이 같은 가게라고 볼 확실한 근거가 있나. 1·2번이 같은 기준을 쓴다."""
    if a["license_no"] and a["license_no"] == b["license_no"]:
        return "license"                       # 같은 인허가번호 체계(모범·식품안심). 결정 4번
    if building(a) and building(a) == building(b):
        if a["tel"] and a["tel"] == b["tel"]:
            return "tel"                       # 전화번호만으로는 본사 대표번호가 겹칠 수 있어 같은 건물일 때만
        if same_name(a, b):
            return "name"
    return ""


class UnionFind:
    """묶음 만들기. union(a, b) 하면 a·b 가 같은 묶음이 된다."""

    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]   # 경로 줄이기: 다음 find 가 빨라진다
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def load_geocode():
    """주소 → (위도, 경도, 출처). geocode.csv 가 아직 없으면 빈 사전."""
    if not os.path.exists(GEOCODE):
        return {}
    with open(GEOCODE, encoding="utf-8") as f:
        return {r["addr"]: (r["lat"], r["lon"], r["source"]) for r in csv.DictReader(f) if r["lat"]}


def main():
    certs = load_certs()
    by_id = {c["cert_id"]: c for c in certs}
    with open(os.path.join(PROCESSED, "matches.csv"), encoding="utf-8") as f:
        stage1 = {r["cert_id"]: r for r in csv.DictReader(f)}
    matched = [c for c in certs if stage1[c["cert_id"]]["store_id"]]
    left = [c for c in certs if not stage1[c["cert_id"]]["store_id"]]

    # 빠르게 찾으려고 열쇠별 색인을 만든다 (2만 × 6만 을 전부 비교하지 않도록)
    by_license, by_bldg = defaultdict(list), defaultdict(list)
    for c in matched:
        if c["license_no"]:
            by_license[c["license_no"]].append(c)
        if building(c):
            by_bldg[building(c)].append(c)

    # ── 1. 물려받기 ──
    result = {}                       # cert_id → (store_id, how)
    stats = Counter()
    rest = []
    for c in left:
        near = by_license.get(c["license_no"], []) + by_bldg.get(building(c), [])
        hits = {}                     # 이어지는 상가업소번호 → 근거
        for o in near:
            why = linked(c, o)
            if why:
                hits.setdefault(stage1[o["cert_id"]]["store_id"], why)
        if len(hits) == 1:
            sid, why = next(iter(hits.items()))
            result[c["cert_id"]] = (sid, "inherit_" + why)
            stats["물려받음 (" + why + ")"] += 1
        else:
            if len(hits) > 1:
                stats["물려받기 보류 (가게 2곳 이상과 이어짐)"] += 1
            rest.append(c)

    # ── 2. 묶기: 같은 건물 안의 남은 인증끼리, 또는 같은 인허가번호 ──
    uf = UnionFind()
    groups_by_key = defaultdict(list)
    for c in rest:
        uf.find(c["cert_id"])
        groups_by_key["b:" + building(c)].append(c) if building(c) else None
        groups_by_key["l:" + c["license_no"]].append(c) if c["license_no"] else None
    for members in groups_by_key.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if a["source"] != b["source"] and linked(a, b):   # 같은 소스끼리는 묶지 않는다 (같은 목록에 두 번 실린 다른 가게일 수 있다)
                    uf.union(a["cert_id"], b["cert_id"])
    groups = defaultdict(list)
    for c in rest:
        groups[uf.find(c["cert_id"])].append(c)

    # ── 3. 새 가게 ──
    index = load_index(certs)
    geocode = load_geocode()
    new_rows = []
    coord_stats = Counter()
    for members in groups.values():
        members.sort(key=lambda c: c["cert_id"])
        sid = "C-" + members[0]["cert_id"]
        rep = min(members, key=lambda c: NAME_PRIORITY.index(c["source"]))   # 이름·주소를 가져올 대표 인증
        lat, lon, src = coords(members, index, geocode)
        coord_stats[src or "없음 (지오코딩 대기)"] += 1
        new_rows.append({
            "store_id": sid, "name": rep["name_raw"], "branch": rep["branch"], "name_norm": rep["name_norm"],
            "food": rep["food_raw"], "sido": rep["sido"], "sgg": rep["sgg_city"], "road_key": building(rep),
            "addr": rep["addr_raw"], "lat": lat, "lon": lon, "coord_source": src,
            "sources": "|".join(sorted({c["source"] for c in members})),
        })
        for c in members:
            result[c["cert_id"]] = (sid, "new_group" if len(members) > 1 else "new")
        stats["새 가게 (인증 2건↑ 묶음)" if len(members) > 1 else "새 가게 (인증 1건)"] += 1

    # ── 저장 ──
    with open(os.path.join(PROCESSED, "cert_store.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cert_id", "store_id", "stage", "how"])
        w.writeheader()
        for c in certs:
            s1 = stage1[c["cert_id"]]
            if s1["store_id"]:
                w.writerow({"cert_id": c["cert_id"], "store_id": s1["store_id"], "stage": "1", "how": s1["reason"]})
            else:
                sid, how = result[c["cert_id"]]
                w.writerow({"cert_id": c["cert_id"], "store_id": sid, "stage": "2", "how": how})
    with open(os.path.join(PROCESSED, "new_stores.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, NEW_COLS)
        w.writeheader()
        w.writerows(new_rows)

    grouped = sum(len(m) for m in groups.values() if len(m) > 1)
    lines = [f"# 2단계 — 상가에서 못 찾은 인증 {len(left):,}건", ""]
    lines += [f"  {k:<28} {v:>7,}" for k, v in stats.most_common()]
    lines += ["", f"  묶음에 들어간 인증 {grouped:,}건 → 새 가게 {len(new_rows):,}곳", "", "새 가게 좌표 출처:"]
    lines += [f"  {k:<28} {v:>7,}" for k, v in coord_stats.most_common()]
    text = "\n".join(lines)
    with open(os.path.join(ROOT, "results", "match_stage2.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


def coords(members, index, geocode):
    """새 가게의 좌표와 출처. 결정 23번 순서: 같은 건물 상가 → 원본 좌표 → 지오코딩."""
    for c in members:
        cands, _ = candidates(c, index)
        if cands:
            # 같은 건물 가게들의 가운데값 (가게마다 좌표가 조금씩 달라서, 튀는 값에 덜 흔들리는 중앙값을 쓴다)
            return (str(statistics.median(float(s["lat"]) for s in cands)),
                    str(statistics.median(float(s["lon"]) for s in cands)), "building")
    for c in members:
        if c["lat"] and c["lon"]:
            return c["lat"], c["lon"], "source"
    for c in members:
        if c["addr_raw"] in geocode:
            return geocode[c["addr_raw"]]
    return "", "", ""


if __name__ == "__main__":
    main()

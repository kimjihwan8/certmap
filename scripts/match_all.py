"""인증 83,922건 전부를 규칙 v1 로 상가에 붙인다. 결정 일지 18·21번.

사용: python3 scripts/match_all.py        (약 1분)
결과: data/processed/matches.csv          인증 1건 = 1행
          cert_id    인증 번호
          store_id   붙은 상가업소번호. 못 찾았으면 빈칸 (2단계에서 처리)
          reason     v1 판정 이유 (same, near_food, no_name …). 확정·보류 이유를 나중에 셀 수 있게 남긴다
          found_by   후보를 어느 건물 키로 찾았나 (road / jibun / 빈칸=건물 없음)
      results/match_all.txt              소스별 확정률, 한 가게에 몰린 인증 수

매칭(이 파일)과 DB 적재(build_db.py)를 나눈 이유:
    - 매칭 결과를 파일로 남겨야 사람이 열어보고 검토할 수 있다
    - DB 구조를 바꿔 다시 적재할 때 매칭을 다시 돌리지 않아도 된다
"""
import csv
import os
from collections import Counter, defaultdict

from match_core import ROOT, candidates, judge_v1, load_certs, load_index

OUT = os.path.join(ROOT, "data", "processed", "matches.csv")
REPORT = os.path.join(ROOT, "results", "match_all.txt")


def main():
    certs = load_certs()
    index = load_index(certs)

    rows = []
    by_source = defaultdict(Counter)       # 소스 → {확정, 미확정} 개수
    reasons = defaultdict(Counter)         # 소스 → 판정 이유별 개수
    for c in certs:
        cands, how = candidates(c, index)
        pick, reason = judge_v1(c, cands)
        rows.append({"cert_id": c["cert_id"], "store_id": pick["store_id"] if pick else "",
                     "reason": reason, "found_by": how})
        by_source[c["source"]]["확정" if pick else "미확정"] += 1
        reasons[c["source"]][reason] += 1

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cert_id", "store_id", "reason", "found_by"])
        w.writeheader()
        w.writerows(rows)

    # 같은 소스의 인증 여러 건이 한 상가 가게에 붙은 경우를 센다.
    # 정상일 수도 있고(식품안심업소가 한 가게에 두 번 지정), 매칭 실수일 수도 있다(같은 건물 다른 가게).
    src_of = {c["cert_id"]: c["source"] for c in certs}
    per_store = Counter((src_of[r["cert_id"]], r["store_id"]) for r in rows if r["store_id"])
    crowded = Counter(src for (src, _), n in per_store.items() if n > 1)
    stores = {r["store_id"] for r in rows if r["store_id"]}

    lines = [f"# 전체 매칭 (규칙 v1) — 인증 {len(rows):,}건", "",
             f"{'소스':<8}{'인증':>8}{'확정':>8}{'확정률':>8}  한 가게에 같은 소스 2건↑"]
    for src, cnt in by_source.items():
        n = cnt["확정"] + cnt["미확정"]
        lines.append(f"{src:<8}{n:>8,}{cnt['확정']:>8,}{cnt['확정'] / n:>8.1%}  {crowded[src]:,}곳")
    total = sum(c["확정"] for c in by_source.values())
    lines += ["", f"확정 {total:,} / {len(rows):,} ({total / len(rows):.1%}), 붙은 상가 가게 {len(stores):,}곳",
              "", "판정 이유 (소스별):"]
    for src, cnt in reasons.items():
        lines.append(f"  {src}: " + ", ".join(f"{k} {v:,}" for k, v in cnt.most_common()))
    text = "\n".join(lines)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
    print(f"\n→ {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()

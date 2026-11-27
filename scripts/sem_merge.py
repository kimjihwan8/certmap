"""의미 검색 판정자 3명(A·B·C)의 답을 다수결로 합친다. 결정 일지 37번.

사용: python3 scripts/sem_merge.py
읽는 것: data/labels/sem_review/labeler_{a,b,c}.csv   (n, query_id, store_id, label, reason)
쓰는 것: data/labels/sem_judgments.csv                 sem_score.py 가 읽는 정답 (사람 판정 도구와 같은 모양)
         data/labels/sem_review/disagreements.md        의견이 갈린 건 (사람이 다시 볼 것)
         results/sem_label_agreement.txt                일치율

최종 정답:
    2명 이상 같은 답   → 그 답 (1 / 0 / U)
    3명이 모두 다름    → U (1·0·U 가 하나씩 = 채점에서 뺀다)
사람 판정 도구로 같은 쌍을 다시 판정하면 그 줄을 덮어쓴다 — 사람 판정이 AI 다수결보다 우선한다.
"""
import csv
import os
from collections import Counter
from itertools import combinations

from merge_labels import fleiss_kappa   # 매칭 정답지 때와 같은 계산

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REVIEW = os.path.join(ROOT, "data", "labels", "sem_review")
OUT = os.path.join(ROOT, "data", "labels", "sem_judgments.csv")
RATERS = ["a", "b", "c"]


def load(rater):
    with open(os.path.join(REVIEW, f"labeler_{rater}.csv"), encoding="utf-8") as f:
        return {(r["query_id"], r["store_id"]): r for r in csv.DictReader(f)}


def main():
    raw = {r: load(r) for r in RATERS}
    keys = list(raw["a"])
    for r in RATERS:
        assert set(raw[r]) == set(keys), f"labeler_{r}: 판정한 쌍이 다른 판정자와 다르다"
        bad = [k for k, v in raw[r].items() if v["label"] not in ("1", "0", "U")]
        assert not bad, f"labeler_{r}: 1/0/U 가 아닌 답 {bad[:3]}"

    final, disagree, pair_ok, rows = [], [], Counter(), []
    for k in keys:
        ans = {r: raw[r][k]["label"] for r in RATERS}
        rows.append([ans[r] for r in RATERS])
        for x, y in combinations(RATERS, 2):
            pair_ok[x + y] += ans[x] == ans[y]
        top, n = Counter(ans.values()).most_common(1)[0]
        label = top if n >= 2 else "U"
        final.append({"query_id": k[0], "store_id": k[1], "label": label, "labeled_at": "AI 3명 독립 판정 다수결"})
        if n < 3:
            disagree.append((k, ans, label))

    # 사람이 판정 도구로 이미 판정한 쌍은 그대로 둔다 (사람 판정이 우선)
    human = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            human = {(r["query_id"], r["store_id"]): r for r in csv.DictReader(f) if not r["labeled_at"].startswith("AI")}
    merged = [human.get((r["query_id"], r["store_id"]), r) for r in final]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["query_id", "store_id", "label", "labeled_at"])
        w.writeheader()
        w.writerows(merged)

    md = ["# 의미 검색 판정 — 의견이 갈린 건", "", f"총 {len(disagree)}건. 2명 이상 같으면 그 답, 셋 다 다르면 U.", ""]
    for (qid, sid), ans, label in disagree:
        md.append(f"## [{qid}] {sid}")
        for r in RATERS:
            md.append(f"- **{r.upper()}** `{ans[r]}` {raw[r][(qid, sid)]['reason']}")
        md.append(f"- 최종 `{label}`")
        md.append("")
    with open(os.path.join(REVIEW, "disagreements.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    dist = Counter(r["label"] for r in final)
    lines = ["# 의미 검색 판정 일치율 (AI 3명 독립 판정)", "",
             f"3명 일치 {len(keys) - len(disagree)} / 갈림 {len(disagree)} (전체 {len(keys)})"]
    lines += [f"  {p[0].upper()}-{p[1].upper()} 일치율 {v / len(keys):.1%}" for p, v in pair_ok.items()]
    lines.append(f"  Fleiss 카파 (1/0/U) {fleiss_kappa(rows, ['1', '0', 'U']):.3f}")
    for r in RATERS:
        c = Counter(v["label"] for v in raw[r].values())
        lines.append(f"  {r.upper()} 분포: 맞음 {c['1']} / 아님 {c['0']} / 애매 {c['U']}")
    lines += ["", f"최종: 맞음 {dist['1']} / 아님 {dist['0']} / 애매 {dist['U']}"
              + (f" (사람 판정 {len(human)}건 우선 적용)" if human else "")]
    text = "\n".join(lines)
    with open(os.path.join(ROOT, "results", "sem_label_agreement.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()

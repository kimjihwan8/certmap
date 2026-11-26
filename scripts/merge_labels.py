"""라벨러 3명(A·B·C)의 라벨을 비교하고, 다수결로 최종 정답지를 만든다. 결정 일지 15번.

사용: python3 scripts/merge_labels.py dev|test

읽는 것: data/labels/{set}_review/labeler_{a,b,c}.csv   (n, item_id, answer, reason)
         data/labels/{set}_items.json            (후보 번호 → 상가업소번호 변환용)
쓰는 것: data/labels/{set}_labels.csv             최종 정답 (label_server 와 같은 형식)
         data/labels/{set}_review/disagreements.md 의견이 갈린 건 목록 (사람이 다시 볼 것)
         results/label_agreement_{set}.txt         일치율

answer 형식 (라벨러 파일):
    '3'      3번 후보가 같은 가게
    '1|2'    상가에 같은 가게가 두 번 실림. 둘 다 정답
    'N'      후보 중에 없음
    'U'      모르겠음

두 라벨이 "같다"의 기준:
    - 둘 다 N, 또는 둘 다 U
    - 둘 다 후보를 골랐고, 고른 번호가 하나라도 겹친다
      ('1|2' 와 '1' 은 같다 — 한 명이 중복을 못 알아챘을 뿐 같은 가게를 가리킨다)

최종 정답:
    3명 모두 같음      → 그 답 (후보를 골랐으면 고른 번호를 모두 합친다)
    2명이 같음         → 그 2명의 답 (다수결)
    3명 모두 다름      → UNSURE (채점에서 뺀다)
    결과가 U           → UNSURE
"""
import csv
import json
import os
import sys
from collections import Counter
from itertools import combinations

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LABELS = os.path.join(ROOT, "data", "labels")
RATERS = ["a", "b", "c"]


def parse(ans):
    """'1|2' → {1, 2}, 'N' → 'N', 'U' → 'U'"""
    ans = ans.strip().upper()
    if ans in ("N", "U"):
        return ans
    return frozenset(int(x) for x in ans.split("|"))


def same(x, y):
    if isinstance(x, frozenset) and isinstance(y, frozenset):
        return bool(x & y)
    return x == y


def coarse(x):
    """번호를 골랐는지 / N / U 세 가지로만 본다 (카파 계산용)"""
    return "pick" if isinstance(x, frozenset) else x


def fleiss_kappa(rows, cats):
    """평가자 여럿의 일치도. 1이면 완전 일치, 0이면 우연히 맞춘 수준.

    rows: 건마다 [평가자1 범주, 평가자2 범주, ...]
    단순 일치율은 "거의 다 pick" 같은 쏠림이 있으면 부풀려지므로, 우연 일치를 뺀 값을 함께 본다.
    """
    n = len(rows[0])
    p_cat = Counter(c for r in rows for c in r)
    total = len(rows) * n
    pe = sum((p_cat[c] / total) ** 2 for c in cats)
    pi = [(sum(v * v for v in Counter(r).values()) - n) / (n * (n - 1)) for r in rows]
    po = sum(pi) / len(pi)
    return (po - pe) / (1 - pe)


def load(review, rater):
    with open(os.path.join(review, f"labeler_{rater}.csv"), encoding="utf-8") as f:
        return {r["item_id"]: r for r in csv.DictReader(f)}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which not in ("dev", "test"):
        sys.exit("사용: python3 scripts/merge_labels.py dev|test")
    review = os.path.join(LABELS, f"{which}_review")
    with open(os.path.join(LABELS, f"{which}_items.json"), encoding="utf-8") as f:
        items = json.load(f)
    raw = {r: load(review, r) for r in RATERS}
    for r in RATERS:
        assert set(raw[r]) == {it["item_id"] for it in items}, f"labeler_{r}: item_id 가 테스트셋과 다르다"

    final, disagree = [], []
    pair_ok = Counter()
    coarse_rows = []
    for n, it in enumerate(items, 1):
        iid = it["item_id"]
        ans = {r: parse(raw[r][iid]["answer"]) for r in RATERS}
        coarse_rows.append([coarse(ans[r]) for r in RATERS])
        for x, y in combinations(RATERS, 2):
            pair_ok[x + y] += same(ans[x], ans[y])

        # 다수결: 나머지 둘 중 하나 이상과 같은 답을 가진 라벨러를 찾는다
        agree = [r for r in RATERS if sum(same(ans[r], ans[o]) for o in RATERS if o != r) >= 1]
        if len(agree) == 3:
            how = "3명 일치"
        elif len(agree) == 2:
            how = "2:1"
        else:
            how = "불일치"
        if agree:
            pick = ans[agree[0]]
            if isinstance(pick, frozenset):
                pick = frozenset().union(*(ans[r] for r in agree))
        else:
            pick = "U"
        if pick == "N":
            answer = "NONE"
        elif pick == "U":
            answer = "UNSURE"
        else:
            answer = "|".join(it["cands"][k - 1]["store_id"] for k in sorted(pick))
        final.append({"item_id": iid, "answer": answer, "memo": how, "labeled_at": "AI 3명 독립 라벨 다수결"})
        if how != "3명 일치":
            disagree.append((n, it, how, {r: raw[r][iid] for r in RATERS}, answer))

    with open(os.path.join(LABELS, f"{which}_labels.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["item_id", "answer", "memo", "labeled_at"])
        w.writeheader()
        w.writerows(final)

    # 의견이 갈린 건: 사람이 다시 볼 수 있게 인증·후보·각자 답과 이유를 한 곳에 모은다
    md = ["# 라벨러 의견이 갈린 건", "", f"총 {len(disagree)}건. 최종 답은 다수결, 3명이 모두 다르면 UNSURE.", ""]
    for n, it, how, rs, answer in disagree:
        c = it["cert"]
        md.append(f"## {n}. [{c['source']}] {c['name_raw']} ({how})")
        md.append(f"- 주소: {c['addr_raw']}")
        for k, s in enumerate(it["cands"], 1):
            md.append(f"- 후보 {k}) {s['name_raw']} {s['branch_raw']} — {s['cat_small']}")
        for r in RATERS:
            md.append(f"- **{r.upper()}**: `{rs[r]['answer']}` {rs[r]['reason']}")
        final_txt = {"NONE": "N", "UNSURE": "U"}.get(answer, answer)
        md.append(f"- 최종: `{final_txt}`")
        md.append("")
    with open(os.path.join(review, "disagreements.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    hows = Counter(d[2] for d in disagree)
    final_c = Counter("NONE" if f["answer"] == "NONE" else "UNSURE" if f["answer"] == "UNSURE" else "가게" for f in final)
    lines = [f"# 라벨 일치율 — {which} (A·B·C 독립 라벨)", "",
             f"3명 일치 {len(items) - len(disagree)} / 2:1 {hows['2:1']} / 불일치 {hows['불일치']}", ""]
    for p, v in pair_ok.items():
        lines.append(f"  {p[0].upper()}-{p[1].upper()} 일치율 {v / len(items):.1%}")
    lines.append(f"  Fleiss 카파 (가게 고름/N/U 세 범주) {fleiss_kappa(coarse_rows, ['pick', 'N', 'U']):.3f}")
    for r in RATERS:
        cnt = Counter(coarse(parse(raw[r][it['item_id']]['answer'])) for it in items)
        lines.append(f"  {r.upper()} 분포: 가게 {cnt['pick']} / N {cnt['N']} / U {cnt['U']}")
    lines += ["", f"최종 정답: 가게 {final_c['가게']} / NONE {final_c['NONE']} / UNSURE {final_c['UNSURE']}"]
    text = "\n".join(lines)
    with open(os.path.join(ROOT, "results", f"label_agreement_{which}.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()

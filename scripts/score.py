"""규칙 판정을 정답지로 채점한다. 결정 일지 16·17번.

사용: python3 scripts/score.py dev  v0 v1    개발용 300건으로 v0·v1 채점 (규칙을 고칠 때 보는 것)
      python3 scripts/score.py test v0 v1    시험용으로 채점 (규칙을 다 고친 뒤 한 번만)
읽는 것: data/labels/{set}_items.json   인증·후보·구간(_stratum)
         data/labels/{set}_labels.csv   정답 (merge_labels.py 결과)
         data/labels/{set}_strata.json  구간별 전체 크기
         상가·인증 정제 표               판정을 지금 코드로 다시 돌린다 (저장된 답을 쓰지 않음)
쓰는 것: results/score_{set}.txt

재는 것 (UNSURE 정답은 뺀다):
    정밀도   규칙이 "같은 가게"라고 확정한 것 중 정답과 같은 비율. 서비스 기준 98% 이상 (결정 일지 7번)
    재현율   정답에 같은 가게가 있는 것 중 규칙이 맞게 찾은 비율
    놓친 몫  정답에 같은 가게가 있는데 규칙이 보류·없음으로 둔 비율 → AI가 건질 수 있는 최대치 (기준 5%)

전체 값은 구간별 값에 "그 구간의 실제 크기"를 곱해 합친다 (층화 추정).
어려운 구간을 일부러 많이 뽑았기 때문에, 300건을 그냥 평균내면 실제보다 나쁘게 나온다.
오차 범위는 구간마다 복원 추출을 4,000번 해서 구한다 (부트스트랩).
"""
import csv
import json
import os
import random
import sys
from collections import defaultdict

from match_core import JUDGES, ROOT, candidates, load_certs, load_index

LABELS = os.path.join(ROOT, "data", "labels")
ORDER = ["same", "tie", "contain", "similar", "none"]
NAMES = {"same": "같은 이름 1곳", "tie": "같은 이름 동점", "contain": "포함", "similar": "비슷함", "none": "맞는 이름 없음"}
BOOT = 4000


def outcome(pick, g):
    """한 건의 채점 결과 (확정했나, 맞게 확정했나, 정답에 가게가 있나, 있는데 못 골랐나)"""
    has = g != "NONE"
    ok = bool(pick) and has and pick in g.split("|")
    return (bool(pick), ok, has, has and not pick)


def estimate(rows, strata, total_pop):
    """구간별 결과를 구간 크기로 가중해 (정밀도, 재현율, 놓친 몫)."""
    e = [0.0] * 4
    for k, rs in rows.items():
        if rs:
            for i in range(4):
                e[i] += strata[k]["population"] * sum(r[i] for r in rs) / len(rs)
    rate = lambda a, b: a / b if b else float("nan")
    return rate(e[1], e[0]), rate(e[1], e[2]), e[3] / total_pop


def score(items, gold, strata, picks, rule):
    rows = defaultdict(list)
    unsure = defaultdict(int)
    wrong = []
    for it in items:
        g = gold[it["item_id"]]
        if g == "UNSURE":
            unsure[it["_stratum"]] += 1
            continue
        pick = picks[it["item_id"]]
        r = outcome(pick, g)
        rows[it["_stratum"]].append(r)
        if r[0] and not r[1]:
            wrong.append((it, pick, g))

    total_pop = sum(strata[k]["population"] for k in ORDER)
    rate = lambda a, b: a / b if b else float("nan")
    lines = [f"## {rule}", "", f"{'구간':<12}{'채점':>5}{'확정':>6}{'정밀도':>9}{'재현율':>9}{'놓친 몫':>9}{'UNSURE':>8}"]
    for k in ORDER:
        rs = rows[k]
        n, picked, right, has, missed = len(rs), *(sum(r[i] for r in rs) for i in range(4))
        lines.append(f"{NAMES[k]:<12}{n:>5}{picked:>6}{rate(right, picked):>9.1%}{rate(right, has):>9.1%}"
                     f"{rate(missed, n):>9.1%}{unsure[k]:>8}")
    p, r, m = estimate(rows, strata, total_pop)

    rng = random.Random(1)
    P, M = [], []
    for _ in range(BOOT):
        smp = {k: [rng.choice(rs) for _ in rs] for k, rs in rows.items()}
        bp, _, bm = estimate(smp, strata, total_pop)
        P.append(bp)
        M.append(bm)
    P.sort()
    M.sort()
    lo, hi = int(BOOT * 0.025), int(BOOT * 0.975) - 1
    lines += ["", "전체 추정 (구간 크기로 가중, 같은 건물 후보가 있는 인증 기준)",
              f"  정밀도  {p:.1%}  (95% {P[lo]:.1%}~{P[hi]:.1%}, 98% 미만일 확률 {sum(x < 0.98 for x in P) / BOOT:.0%})",
              f"  재현율  {r:.1%}",
              f"  놓친 몫 {m:.1%}  (95% {M[lo]:.1%}~{M[hi]:.1%}, 5% 이상일 확률 {sum(x >= 0.05 for x in M) / BOOT:.0%})",
              "", f"틀리게 확정한 건 ({len(wrong)})"]
    for it, pick, g in wrong:
        c = it["cert"]
        name = {s["store_id"]: s for s in it["cands"]}
        pn = name[pick]["name_raw"] if pick in name else f"(목록 밖 {pick})"
        right = "없음" if g == "NONE" else ", ".join(name[x]["name_raw"] for x in g.split("|") if x in name)
        lines.append(f"  [{NAMES[it['_stratum']]}] {c['source']} {c['name_raw']} → 규칙: {pn} / 정답: {right}")
    return lines, (p, r, m)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("dev", "test"):
        sys.exit("사용: python3 scripts/score.py dev|test v0 [v1 …]")
    which, rules = sys.argv[1], sys.argv[2:]
    with open(os.path.join(LABELS, f"{which}_items.json"), encoding="utf-8") as f:
        items = json.load(f)
    with open(os.path.join(LABELS, f"{which}_labels.csv"), encoding="utf-8") as f:
        gold = {r["item_id"]: r["answer"] for r in csv.DictReader(f)}
    with open(os.path.join(LABELS, f"{which}_strata.json"), encoding="utf-8") as f:
        strata = json.load(f)

    # 판정은 저장된 답이 아니라 지금 코드로 다시 돌린다 (건물 안 후보 전체가 필요하다)
    want = {it["item_id"] for it in items}
    certs = [c for c in load_certs() if c["cert_id"] in want]
    index = load_index(certs)
    by_id = {c["cert_id"]: c for c in certs}

    out = [f"# 규칙 채점 — {which} ({len(items)}건)", "",
           "UNSURE 정답은 뺐다. 정밀도 = 맞게 확정 / 확정, 재현율 = 맞게 확정 / 정답에 가게 있음", ""]
    summary = []
    for rule in rules:
        judge = JUDGES[rule]
        picks = {}
        for iid in want:
            c = by_id[iid]
            pick, _ = judge(c, candidates(c, index)[0])
            picks[iid] = pick["store_id"] if pick else ""
        lines, (p, r, m) = score(items, gold, strata, picks, rule)
        out += lines + [""]
        summary.append(f"  {rule}: 정밀도 {p:.1%} / 재현율 {r:.1%} / 놓친 몫 {m:.1%}")
    out = out[:4] + ["## 요약"] + summary + [""] + out[4:]
    text = "\n".join(out)
    path = os.path.join(ROOT, "results", f"score_{which}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()

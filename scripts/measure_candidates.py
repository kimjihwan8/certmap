"""판정 규칙을 정하기 전에, 인증 하나당 상가 후보가 어떻게 나오는지 잰다.

질문:
    1. 같은 건물 후보를 아예 못 찾는 인증은 몇 %인가?           → 주소 문제 또는 상가에 없는 가게
    2. 같은 건물에 상가 가게가 보통 몇 곳 있나?                → 이름 비교가 얼마나 어려운지
    3. 후보 중 이름이 가장 잘 맞는 수준은 어디까지인가?          → 어느 규칙까지 필요한지 (수준은 match_core.LEVELS)
    4. 가장 잘 맞는 후보가 2곳 이상인 경우는 몇 %인가?          → 업종으로 판가름해야 하는 경우
    5. 규칙 판정(judge_v0)은 각 경우를 몇 %씩 내나?

사용: python3 scripts/measure_candidates.py   (약 10초)
결과: results/candidates_profile.txt
"""
import os
import statistics
from collections import Counter, defaultdict

from match_core import LEVELS, ROOT, candidates, dice, judge_v0, level, load_certs, load_index

OUT = os.path.join(ROOT, "results", "candidates_profile.txt")
REASONS = ["same", "same_tie_food", "near_food", "tie", "near_hold", "no_name", "no_bldg"]


def main():
    certs = load_certs()
    index = load_index(certs)

    stat = defaultdict(Counter)          # 소스 → 개수 세기
    ncand = defaultdict(list)            # 소스 → 건물 안 후보 수 목록
    examples = defaultdict(list)         # 수준 → 예시 몇 개
    for c in certs:
        src = c["source"]
        stat[src]["total"] += 1
        cands, _ = candidates(c, index)
        _, reason = judge_v0(c, cands)
        stat[src]["r:" + reason] += 1
        if not cands:
            continue
        ncand[src].append(len(cands))
        lv = [level(c, s) for s in cands]
        best = min(lv, key=LEVELS.index)
        stat[src][best] += 1
        tied = [s for s, l in zip(cands, lv) if l == best]
        if best != "none" and len(tied) >= 2:
            stat[src]["tie"] += 1
        if best not in ("none", "exact") and len(examples[best]) < 8:
            examples[best].append(f"{src} | {c['name_raw']} → {tied[0]['name_raw']} {tied[0]['branch_raw']} ({tied[0]['cat_small']})")
        if best == "none" and len(examples["none"]) < 8:
            near = max(cands, key=lambda s: dice(c["name_norm"], s["name_norm"]))
            examples["none"].append(f"{src} | {c['name_raw']} → 가장 비슷한 후보: {near['name_raw']} (후보 {len(cands)}곳)")

    order = sorted(stat, key=lambda s: -stat[s]["total"])
    lines = ["# 인증 → 상가 후보 프로필", "",
             "## 1. 이름 비교 수준 ('건물을 찾은 인증' 중 비율. 동점 = 가장 잘 맞는 후보가 2곳 이상)", ""]
    lines.append(f"{'소스':<8}{'전체':>7}{'건물못찾음':>9}{'후보중앙값':>8}" + "".join(f"{l:>9}" for l in LEVELS) + f"{'동점':>8}")
    for src in order:
        st = stat[src]
        found = st["total"] - st["r:no_bldg"]
        row = f"{src:<8}{st['total']:>7,}{st['r:no_bldg'] / st['total']:>11.1%}{statistics.median(ncand[src]):>10}"
        row += "".join(f"{st[l] / found:>9.1%}" for l in LEVELS) + f"{st['tie'] / found:>8.1%}"
        lines.append(row)

    lines += ["", "## 2. 규칙 판정 judge_v0 (전체 중 비율)", ""]
    lines.append(f"{'소스':<8}" + "".join(f"{r:>15}" for r in REASONS) + f"{'확정 합계':>11}")
    for src in order:
        st = stat[src]
        n = st["total"]
        done = st["r:same"] + st["r:same_tie_food"] + st["r:near_food"]
        lines.append(f"{src:<8}" + "".join(f"{st['r:' + r] / n:>15.1%}" for r in REASONS) + f"{done / n:>11.1%}")

    lines += ["", "## 3. 수준별 예시 (인증 이름 → 상가 후보)"]
    for l in LEVELS[1:]:
        lines.append(f"\n[{l}]")
        lines += [f"  {e}" for e in examples[l]]
    text = "\n".join(lines)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()

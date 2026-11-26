"""정답지 300건을 뽑는다. 결정 일지 14·17번.

정답지는 두 벌이다:
    dev   개발용. 규칙을 고칠 때 틀린 사례를 들여다보는 데 쓴다. (처음 뽑은 300건, 시드 20261124)
    test  시험용. dev 와 겹치지 않게 새로 뽑고, 규칙을 다 고친 뒤 한 번만 채점한다. (시드 20261125)
    dev 를 보며 규칙을 고치면 dev 점수는 실제보다 좋게 나온다. 그래서 진짜 성적은 test 로 잰다.

한 건 = 인증 1개 + 같은 건물 상가 후보 최대 9곳. 라벨링하는 사람은 후보 중 같은 가게를 고르거나 "없음"을 고른다.
(쌍마다 O/X를 매기는 것보다 빠르고, "후보에 정답이 아예 없다"도 기록할 수 있다)

구간별로 뽑는 수 (어려운 구간을 더 많이):
    same     같은 이름 후보 1곳            60
    tie      같은 이름 후보 2곳 이상        40
    contain  가장 잘 맞는 게 '포함'         70
    similar  가장 잘 맞는 게 '비슷함'       70
    none     맞는 이름 없음               60
    (같은 건물 후보가 0곳인 인증은 고를 후보가 없어 뽑지 않는다)

구간마다 뽑는 비율이 다르므로, 나중에 전체 정밀도를 낼 때는 구간별 결과에
"그 구간의 실제 크기"를 곱해서 합친다. 그래서 구간 크기를 {set}_strata.json 에 함께 저장한다.
구간은 두 벌 모두 v0 의 이름 비교 수준으로 나눈다 (같은 기준으로 뽑아야 v0·v1 을 공정하게 비교한다).

공정하게 라벨링하려고:
    - 순서를 섞는다 (구간이 안 보이게)
    - 규칙이 고른 답과 이름 비교 수준을 화면에 보여주지 않는다 (규칙 답에 끌려가지 않게)
    - 이미 뽑은 정답지는 덮어쓰지 않는다. 라벨을 단 뒤에 바뀌면 숫자를 비교할 수 없다.

사용: python3 scripts/make_pairs.py test      (약 10초, 이미 있으면 멈춤)
결과: data/labels/{set}_items.json       라벨링 도구가 읽는 300건
      data/labels/{set}_strata.json      구간별 전체 크기와 뽑은 수
      data/labels/{set}_review/items.md  라벨러가 읽는 텍스트 (번호 = 라벨 파일의 n)
"""
import json
import os
import random
import sys
from collections import defaultdict

from match_core import LEVELS, ROOT, SAME_NAME, candidates, dice, judge_v0, level, load_certs, load_index

OUT_DIR = os.path.join(ROOT, "data", "labels")
QUOTA = {"same": 60, "tie": 40, "contain": 70, "similar": 70, "none": 60}
MAX_CANDS = 9      # 화면에서 숫자키 1~9로 고르므로 9곳까지
SEEDS = {"dev": 20261124, "test": 20261125}   # 같은 시드 → 같은 300건 (재현 가능)

CERT_SHOW = ("cert_id", "source", "name_raw", "branch", "addr_raw", "food_raw", "menu", "tel", "sido", "sgg_city")
CAND_SHOW = ("store_id", "name_raw", "branch_raw", "cat_mid", "cat_small", "sgg", "bldg_name", "floor", "lat", "lon")


def stratum(c, cands):
    """인증 한 건이 어느 구간에 속하는지. 후보가 없으면 None (뽑지 않음)."""
    if not cands:
        return None
    lv = [level(c, s) for s in cands]
    best = min(lv, key=LEVELS.index)
    if best in SAME_NAME:
        return "same" if lv.count(best) == 1 else "tie"
    return best   # contain / similar / none


def ranked(c, cands):
    """후보를 이름이 잘 맞는 순으로 정렬해 앞의 MAX_CANDS 곳만 남긴다.

    큰 건물은 후보가 100곳이 넘기도 해서 다 보여줄 수 없다.
    정답이 9곳 밖에 있으면 라벨링하는 사람이 "없음"을 고르게 되는데,
    그 경우는 이름이 전혀 안 닮은 가게라 규칙·AI도 못 찾는 경우다.
    """
    key = lambda s: (LEVELS.index(level(c, s)), -dice(c["name_norm"], s["name_norm"]))
    return sorted(cands, key=key)[:MAX_CANDS]


def review_text(items):
    """라벨러(사람·AI)가 읽을 텍스트. 규칙이 고른 답(_ 로 시작하는 필드)은 넣지 않는다."""
    out = []
    for n, it in enumerate(items, 1):
        c = it["cert"]
        t = f"### {n}. {it['item_id']}\n인증: [{c['source']}] {c['name_raw']}" + (f" / 지점 {c['branch']}" if c["branch"] else "")
        t += f"\n주소: {c['addr_raw']}"
        if c["food_raw"]:
            t += f"\n업종: {c['food_raw']}"
        if c["menu"]:
            t += f"\n메뉴: {c['menu'][:80]}"
        more = f" (건물 전체 {it['n_cands_total']}곳 중 이름이 비슷한 {len(it['cands'])}곳)" if it["n_cands_total"] > len(it["cands"]) else ""
        t += f"\n후보{more}:"
        for i, s in enumerate(it["cands"], 1):
            extra = " · ".join(x for x in [s["cat_mid"] + "/" + s["cat_small"], s["floor"] + "층" if s["floor"] else "", s["bldg_name"]] if x)
            t += f"\n  {i}) {s['name_raw']}" + (f" [{s['branch_raw']}]" if s["branch_raw"] else "") + f" — {extra}"
        out.append(t)
    return "\n\n".join(out) + "\n"


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which not in SEEDS:
        sys.exit("사용: python3 scripts/make_pairs.py dev|test")
    items_path = os.path.join(OUT_DIR, f"{which}_items.json")
    strata_path = os.path.join(OUT_DIR, f"{which}_strata.json")
    if os.path.exists(items_path) and "--force" not in sys.argv:
        sys.exit(f"이미 있다: {items_path}\n정답지는 한 번 뽑으면 고정한다. 정말 다시 뽑으려면 --force")
    # test 는 dev 에 나온 인증을 빼고 뽑는다 (같은 문제가 두 시험지에 나오면 안 된다)
    exclude = set()
    if which == "test":
        with open(os.path.join(OUT_DIR, "dev_items.json"), encoding="utf-8") as f:
            exclude = {it["item_id"] for it in json.load(f)}
    certs = load_certs()
    index = load_index(certs)

    pool = defaultdict(list)   # 구간 → [(인증, 후보들, 규칙 판정)]
    size = defaultdict(int)    # 구간 → 전체 크기 (가중치용이라 dev 에 나온 것도 센다)
    for c in certs:
        cands, how = candidates(c, index)
        st = stratum(c, cands)
        if st:
            size[st] += 1
            if c["cert_id"] not in exclude:
                pick, reason = judge_v0(c, cands)
                pool[st].append((c, cands, how, pick, reason))

    rng = random.Random(SEEDS[which])
    items = []
    for st, n in QUOTA.items():
        for c, cands, how, pick, reason in rng.sample(pool[st], n):
            items.append({
                "item_id": c["cert_id"],
                "cert": {k: c[k] for k in CERT_SHOW},
                "cands": [{k: s[k] for k in CAND_SHOW} for s in ranked(c, cands)],
                "n_cands_total": len(cands),
                # 아래는 채점용. 라벨링 화면에는 보여주지 않는다
                "_stratum": st, "_found_by": how,
                "_v0_pick": pick["store_id"] if pick else "", "_v0_reason": reason,
            })
    rng.shuffle(items)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(items_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    strata = {st: {"population": size[st], "sampled": QUOTA[st]} for st in QUOTA}
    with open(strata_path, "w", encoding="utf-8") as f:
        json.dump(strata, f, ensure_ascii=False, indent=1)
    review = os.path.join(OUT_DIR, f"{which}_review")
    os.makedirs(review, exist_ok=True)
    with open(os.path.join(review, "items.md"), "w", encoding="utf-8") as f:
        f.write(review_text(items))

    print(f"{len(items)}건 → {os.path.normpath(items_path)}")
    for st, v in strata.items():
        print(f"  {st:<8} 전체 {v['population']:>6,} 중 {v['sampled']}건")


if __name__ == "__main__":
    main()

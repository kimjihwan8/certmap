"""인증 → 상가 매칭의 공통 부품. 측정·정답지·판정 스크립트가 모두 이 파일을 쓴다.

흐름 (인증 한 건):
    1. candidates   같은 건물에 있는 상가 가게를 모은다 (도로명 키 → 없으면 지번 키), 시군구가 다르면 뺀다
    2. level        후보마다 이름이 어느 수준으로 맞는지 매긴다
    3. judge_v0     규칙으로 같은 가게 하나를 고르거나, 못 고르면 이유를 남긴다

함수 목록:
    bigrams, dice   이름 유사도 (글자 2개 묶음이 겹치는 정도)
    level           인증·후보 한 쌍의 이름 비교 수준
    load_index      상가 중 인증과 같은 건물 키를 가진 가게만 메모리에 올린다
    candidates      인증 한 건의 같은 건물 후보 목록
    judge_v0        규칙 판정 (결정 일지 13번)
    judge_v1        규칙 판정 v1 (결정 일지 17번): 지점 충돌·건물 공통 글자·중복 등재 처리
"""
import csv
import os
import re
from collections import defaultdict

from normalize import name_norm

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CERTS = os.path.join(ROOT, "data", "processed", "certs.csv")
SANGGA = os.path.join(ROOT, "data", "processed", "sangga.csv")

# 이름 비교 수준. 위에 있을수록 확실하다. 후보 하나에 대해 먼저 맞는 것 하나만 매긴다.
#   exact    정규화한 이름이 같다          '(주)고려회관' = '고려회관'
#   full     인증 이름 = 상가 상호명+지점명  '곽만근갈비탕평내점' = '곽만근갈비탕' + '평내점'
#   core     지점명을 뗀 본이름이 같다      '고려회관 본점' = '고려회관'
#   contain  한쪽이 다른 쪽을 포함한다       '청진옥' ⊃ '청진'  ← 다른 가게일 수도 있다
#   similar  글자 2개 묶음 유사도 0.5 이상  '미도리회집' ≈ '미도리횟집'
#   none     위에 하나도 해당 없음
LEVELS = ["exact", "full", "core", "contain", "similar", "none"]
SAME_NAME = {"exact", "full", "core"}   # 이름이 '같다'고 보는 수준
NEAR_NAME = {"contain", "similar"}      # 이름이 '비슷하다' — 애매한 구간
SIMILAR_MIN = 0.5

# 후보를 메모리에 올릴 때 남기는 상가 열
_KEEP = ("store_id", "name_raw", "branch_raw", "name_norm", "name_core", "name_full_norm",
         "cat_large", "cat_mid", "cat_small", "sgg", "sgg_city", "bldg_name", "floor", "lon", "lat")


def bigrams(s):
    """'고려회관' → {'고려', '려회', '회관'}. 한 글자 이름은 그 글자 하나."""
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def dice(a, b):
    """두 이름이 겹치는 정도 (0~1). 글자 2개 묶음이 얼마나 겹치나.

    편집거리보다 단순하고, 짧은 한국어 상호에서 글자 하나가 달라도('회집'/'횟집') 꽤 높게 나온다.
    """
    if not a or not b:
        return 0.0
    x, y = bigrams(a), bigrams(b)
    return 2 * len(x & y) / (len(x) + len(y))


def level(c, s):
    """인증 c 와 상가 후보 s 의 이름이 어느 수준으로 맞는지 LEVELS 중 하나로 돌려준다."""
    if c["name_norm"] and c["name_norm"] == s["name_norm"]:
        return "exact"
    if c["name_norm"] and c["name_norm"] == s["name_full_norm"]:
        return "full"
    if c["name_core"] and c["name_core"] == s["name_core"]:
        return "core"
    a, b = c["name_core"], s["name_core"]
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
        return "contain"
    if dice(c["name_norm"], s["name_norm"]) >= SIMILAR_MIN:
        return "similar"
    return "none"


def load_certs():
    with open(CERTS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_index(certs):
    """상가 277만 중 인증 쪽에 나온 건물 키를 가진 가게만 메모리에 올린다.

    돌려주는 것: (도로명 키 → 가게 목록, 지번 키 → 가게 목록)
    전부 올리면 메모리를 많이 쓰고, 어차피 인증과 같은 건물인 가게만 후보가 된다.
    """
    road_need = {c["road_key"] for c in certs if c["road_key"]}
    jibun_need = {c["jibun_key"] for c in certs if c["jibun_key"]}
    by_road, by_jibun = defaultdict(list), defaultdict(list)
    with open(SANGGA, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            in_road, in_jibun = r["road_key"] in road_need, r["jibun_key"] in jibun_need
            if in_road or in_jibun:
                s = {k: r[k] for k in _KEEP}
                if in_road:
                    by_road[r["road_key"]].append(s)
                if in_jibun:
                    by_jibun[r["jibun_key"]].append(s)
    return by_road, by_jibun


def candidates(c, index):
    """인증 c 와 같은 건물에 있는 상가 가게 목록과, 어느 키로 찾았는지('road'/'jibun'/'')를 돌려준다.

    시군구 필터:
        건물 키에는 시군구가 없다(결정 일지 5번). 그래서 충청북도 '중앙로 46'이
        충주시 중앙로와 제천시 중앙로를 함께 가리킬 수 있다.
        인증의 시군구가 상가 목록과 맞춰진 경우(sgg_ok)에만, 시군구가 다른 후보를 뺀다.
        못 맞춘 경우(인천 옛 '중구' 등)는 빼지 않는다.
    """
    by_road, by_jibun = index
    for how, found in (("road", by_road.get(c["road_key"])), ("jibun", by_jibun.get(c["jibun_key"]))):
        if not found:
            continue
        if c["sgg_ok"] == "1":
            found = [s for s in found if s["sgg_city"] == c["sgg_city"]]
        if found:
            return found, how
    return [], ""


def judge_v0(c, cands):
    """규칙 판정. (고른 상가 가게 또는 None, 이유) 를 돌려준다. 결정 일지 13번.

    ① 같은 이름 후보가 1곳                      → 그 가게           'same'
    ② 같은 이름 후보가 여럿, 그중 음식 업종이 1곳  → 그 가게           'same_tie_food'
       음식 업종이 0곳이거나 여럿                 → 보류             'tie'
    ③ 비슷한 이름 후보 중 음식 업종이 1곳          → 그 가게           'near_food'
       음식 업종이 아니거나 여럿                  → 보류             'near_hold'
    ④ 맞는 이름 없음                             → 상가에 없음       'no_name'
       같은 건물 후보 없음                         → 상가에 없음       'no_bldg'

    ③에서 업종을 보는 이유: '(주)조선호텔앤리조트 스시조' → '조선호텔앤리조트'(호텔),
    '남도미항 용산아이파크몰점' → '용산아이파크헤지스'(의류)처럼 비슷한 이름의 비식당이 오답으로 걸린다.
    """
    if not cands:
        return None, "no_bldg"
    lv = [level(c, s) for s in cands]
    best = min(lv, key=LEVELS.index)
    if best == "none":
        return None, "no_name"
    group = SAME_NAME if best in SAME_NAME else NEAR_NAME
    # 같은 그룹 안에서는 가장 잘 맞는 수준의 후보만 본다
    tied = [s for s, l in zip(cands, lv) if l == best]
    if best in SAME_NAME:
        if len(tied) == 1:
            return tied[0], "same"
        food = [s for s in tied if s["cat_large"] == "음식"]
        return (food[0], "same_tie_food") if len(food) == 1 else (None, "tie")
    near = [s for s, l in zip(cands, lv) if l in group]
    food = [s for s in near if s["cat_large"] == "음식"]
    return (food[0], "near_food") if len(food) == 1 else (None, "near_hold")


# ════════════════════════════════════════════════════════════════════
# v1 (결정 일지 17번) — 개발용 300건에서 찾은 v0의 약점 세 가지를 고쳤다
# ════════════════════════════════════════════════════════════════════

COMMON_MIN = 3   # 같은 건물 후보 몇 곳 이상의 이름에 나오면 '건물에서 흔한 글자 묶음'으로 보나


def common_bigrams(cands):
    """같은 건물 후보 COMMON_MIN 곳 이상의 이름에 나오는 글자 2개 묶음.

    백화점·휴게소·역세권 건물은 가게 이름 뒤에 위치를 붙인다:
        '얌샘선유도역점', '돼지대첩영등포선유도역점', '담소소사골순대선유도역점' …
    이때 '선유','유도','도역','역점'은 가게가 아니라 위치를 말하므로 이름 비교에서 뺀다.
    (검색의 IDF와 같은 생각 — 흔한 단어일수록 구별하는 힘이 약하다)
    """
    df = {}
    for s in cands:
        for g in set(bigrams(s["name_norm"])):
            df[g] = df.get(g, 0) + 1
    return {g for g, n in df.items() if n >= COMMON_MIN}


def dice_local(a, b, common):
    """dice 와 같지만 건물에서 흔한 묶음을 빼고 비교한다. 빼고 나서 남는 게 없으면 0."""
    x, y = bigrams(a) - common, bigrams(b) - common
    if not x or not y:
        return 0.0
    return 2 * len(x & y) / (len(x) + len(y))


def branch_conflict(c, s):
    """인증 지점과 상가 이름의 나머지 부분이 서로 다른 지점을 가리키면 True.

    '포함' 수준에서만 쓴다. 인증 본이름이 상가 이름에 들어 있을 때, 상가 이름에서
    본이름을 뺀 나머지(+상가 지점명)를 인증 지점과 비교한다.
        '롯데리아 언더랜드점' vs '롯데리아키자니아'          나머지 '키자니아' ≠ '언더랜드점'  → 충돌
        '한옥집김치찜 인천공항제1터미널점' vs '…제2 [터미널점]'  숫자 1 ≠ 2                    → 충돌
        '공차(롯데아울렛 파주점)' vs '공차파주점 [롯데아울렛]'   나머지가 지점과 거의 같다       → 충돌 아님
    """
    b = name_norm(c["branch"])
    core = c["name_core"]
    if not b or not core or core not in s["name_full_norm"]:
        return False
    rest = s["name_full_norm"].replace(core, "", 1)
    if not rest:
        return False
    digits = lambda t: set(re.findall(r"\d+", t))
    if digits(rest) and digits(b) and digits(rest) != digits(b):
        return True
    return dice(rest, b) < 0.5


def level_v1(c, s, common):
    """level 과 같은 순서지만 '포함'과 '비슷함'을 더 엄격하게 본다.

    ① 지점 충돌이면 바로 none                  '롯데리아 언더랜드점' vs '롯데리아키자니아'
    ② 한쪽 이름이 건물에서 흔한 묶음뿐이면 포함 아님  '시흥하늘휴게소교동도나스' vs '시흥하늘휴게소'
       (후보 이름이 가게가 아니라 위치 이름이다)
    ③ 비슷함은 인증 지점명을 양쪽에서 떼고, 흔한 묶음을 뺀 뒤 잰다
       '굽네치킨(여주대점)' vs '호식이두마리치킨여주대점' → '굽네치킨' vs '호식이두마리치킨'
    """
    lv = level(c, s)
    if lv in SAME_NAME:
        return lv
    if branch_conflict(c, s):
        return "none"
    a, b = c["name_core"], s["name_core"]
    only_place = lambda t: not (bigrams(t) - common)
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a) and not only_place(a) and not only_place(b):
        return "contain"
    branch = name_norm(c["branch"])
    rest = s["name_norm"].replace(branch, "") if branch else s["name_norm"]
    if dice_local(a, rest, common) >= SIMILAR_MIN:
        return "similar"
    return "none"


def _all_same(stores):
    """후보들이 상가에 같은 가게가 여러 번 실린 것인지 (이름·지점명이 모두 같음)."""
    return len({(s["name_norm"], s["branch_raw"]) for s in stores}) == 1


def judge_v1(c, cands):
    """규칙 판정 v1. judge_v0 과 같은 틀에 세 가지를 바꿨다.

    ① 이름 비교: level_v1 (지점 충돌 거르기, 건물에서 흔한 글자 묶음 빼기)
    ② 같은 이름 동점인데 후보가 모두 똑같은 이름·지점이면 → 첫 번째를 고른다  'same_dup'
       (상가에 같은 가게가 두 번 실린 것. 어느 쪽을 골라도 같은 가게)
    ③ 비슷한 이름 중 음식 업종이 여럿이어도 모두 똑같은 이름이면 → 첫 번째       'near_dup'
    """
    if not cands:
        return None, "no_bldg"
    common = common_bigrams(cands)
    lv = [level_v1(c, s, common) for s in cands]
    best = min(lv, key=LEVELS.index)
    if best == "none":
        return None, "no_name"
    tied = [s for s, l in zip(cands, lv) if l == best]
    if best in SAME_NAME:
        if len(tied) == 1:
            return tied[0], "same"
        food = [s for s in tied if s["cat_large"] == "음식"]
        if len(food) == 1:
            return food[0], "same_tie_food"
        if _all_same(food or tied):
            return (food or tied)[0], "same_dup"
        return None, "tie"
    near = [s for s, l in zip(cands, lv) if l in NEAR_NAME]
    food = [s for s in near if s["cat_large"] == "음식"]
    if len(food) == 1:
        return food[0], "near_food"
    if len(food) > 1 and _all_same(food):
        return food[0], "near_dup"
    return None, "near_hold"


JUDGES = {"v0": judge_v0, "v1": judge_v1}

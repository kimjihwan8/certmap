"""참고 레포(yeodusung-ux/korea-restaurant-certs) build_site.py 의 similar() 를 모범음식점 ↔ 상가에 적용한 베이스라인."""
import sys, re, random
from collections import Counter
sys.path.insert(0, "/Users/kimjihwan/restaurant-map/scripts")
import measure_exact_match as m

# 참고 레포 build_site.py 의 core()/similar() 그대로
NON = re.compile(r"[^0-9A-Za-z가-힣]"); BR = re.compile(r"(본점|직영점|지점|점)$")
def core(s):
    k = NON.sub("", s or "").lower()
    for _ in range(2): k = BR.sub("", k)
    return k
def similar(a, b):
    ca, cb = core(a), core(b)
    if not ca or not cb: return False
    if ca == cb: return True
    if len(ca) >= 3 and len(cb) >= 3 and (ca in cb or cb in ca): return True
    sa, sb = set(ca), set(cb)
    return min(len(ca), len(cb)) >= 4 and len(sa & sb) / len(sa | sb) >= 0.75

rows = m.load_mobum()
n, _, _, by_addr, _ = m.load_sangga()
c = Counter(); random.seed(3); multi = []; newly = []
for name, sido, sgg, addr in rows:
    k = m.road_key(sido, sgg.split()[0] if sgg else "", addr.replace(sido, "", 1))
    cands = by_addr.get(k, []) if k else []
    exact = any(name.strip() in (a, b) for a, b, _ in cands)
    hits = [b for a, b, cat in cands if similar(name, a) or similar(name, b)]
    c["total"] += 1; c["exact"] += exact; c["sim"] += bool(hits)
    if len(set(hits)) > 1: c["multi"] += 1; multi.append((name, sorted(set(hits))[:4]))
    if hits and not exact: newly.append((name, hits[0]))
t = c["total"]
print(f"모범음식점 {t:,}건 (같은 건물 블로킹)")
print(f"  같은 건물+완전일치      {c['exact']/t*100:.1f}%")
print(f"  같은 건물+참고레포 similar {c['sim']/t*100:.1f}%")
print(f"  similar 후보가 2개 이상    {c['multi']:,}건 ({c['multi']/t*100:.1f}%)")
print("\n[similar 로 새로 붙은 것 샘플]")
for a, b in random.sample(newly, 25): print(f"  {a}  ↔  {b}")
print("\n[후보 여러 개 샘플]")
for a, b in random.sample(multi, 10): print(f"  {a}  →  {b}")

"""의미 검색 채점: 모델마다 상위 5곳 중 맞은 비율(정밀도@5) + 속도·메모리 한 표. 결정 일지 34·35번.

사용: python3 scripts/sem_score.py      → results/sem_score.txt
읽는 것: data/labels/sem_pool.csv       (방식별 순위, packages/db 의 sem-pool)
         data/labels/sem_judgments.csv  (사람 판정, scripts/sem_label_server.py)
         data/labels/sem_queries.csv    (질문 종류별로 나눠 보려고)
         results/sem_bench.json         (모델별 속도·메모리, sem-pool 이 잰다)

정밀도@5 = 상위 5곳 중 '맞음' 수 / (상위 5곳 중 판정이 '맞음' 또는 '아님'인 수)
    '애매(U)'와 아직 판정 안 한 건은 분모에서 뺀다. 판정 안 한 건이 있으면 몇 건인지 같이 적는다.
질문마다 정밀도를 내고 평균한다 (질문 하나하나를 같은 무게로).
"""
import csv
import json
import os
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LABELS = os.path.join(ROOT, "data", "labels")
OUT = os.path.join(ROOT, "results", "sem_score.txt")


def read(name):
    with open(os.path.join(LABELS, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    queries = {q["query_id"]: q for q in read("sem_queries.csv")}
    judged = {(r["query_id"], r["store_id"]): r["label"] for r in read("sem_judgments.csv")} \
        if os.path.exists(os.path.join(LABELS, "sem_judgments.csv")) else {}
    ranks = defaultdict(lambda: defaultdict(list))        # 방식 → 질문 → [가게 …] (순위대로)
    for p in sorted(read("sem_pool.csv"), key=lambda p: int(p["rank"])):
        ranks[p["system"]][p["query_id"]].append(p["store_id"])

    lines = ["# 의미 검색 채점 — 정밀도@5 (상위 5곳 중 소개글 근거로 맞는 곳의 비율)", ""]
    summary = {}                                          # 모델 → 평균 정밀도 (맨 위 표에 쓴다)
    for system, by_q in ranks.items():
        per_q, missing = {}, 0
        for qid, stores in by_q.items():
            labels = [judged.get((qid, s)) for s in stores[:5]]
            missing += sum(l is None for l in labels)
            counted = [l for l in labels if l in ("1", "0")]
            if counted:
                per_q[qid] = sum(l == "1" for l in counted) / len(counted)
        if not per_q:
            lines.append(f"{system}: 판정한 건이 아직 없다")
            continue
        avg = sum(per_q.values()) / len(per_q)
        summary[system] = (avg, len(per_q), missing)
        lines.append(f"## {system}: 평균 {avg:.0%}  (질문 {len(per_q)}개" + (f", 판정 안 한 건 {missing}개" if missing else "") + ")")
        by_kind = defaultdict(list)
        for qid, v in per_q.items():
            by_kind[queries[qid]["kind"]].append(v)
        lines.append("  종류별: " + " / ".join(f"{k} {sum(v) / len(v):.0%}" for k, v in by_kind.items()))
        for qid in sorted(per_q):
            lines.append(f"  {qid} {queries[qid]['query']:<14} {per_q[qid]:.0%}")
        lines.append("")
    # 맨 위에 한 표: 정확도와 배포 비용(메모리·응답 시간)을 같이 본다 (결정 35번)
    bench_path = os.path.join(ROOT, "results", "sem_bench.json")
    bench = json.load(open(bench_path, encoding="utf-8")) if os.path.exists(bench_path) else {}
    table = ["| 모델 | 정밀도@5 | 검색어 응답 | 서비스 메모리 | 모델 파일 |", "|---|---|---|---|---|"]
    for system in sorted(set(summary) | set(bench), key=lambda m: bench.get(m, {}).get("fileMb", 0)):
        b, sc = bench.get(system, {}), summary.get(system)
        p5 = f"{sc[0]:.0%}" + (f" (미판정 {sc[2]})" if sc and sc[2] else "") if sc else "판정 전"
        table.append(f"| {system} | {p5} | {b.get('queryMsMedian', '?')}ms | {b.get('rssServeMb', '?')}MB | {b.get('fileMb', '?')}MB |")
    lines = lines[:2] + table + [""] + lines[2:]
    text = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()

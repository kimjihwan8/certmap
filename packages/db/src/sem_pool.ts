/**
 * 의미 검색 비교 실험 — 모델 하나를 돌려 (1) 판정할 후보를 모으고 (2) 속도·메모리를 잰다. 결정 일지 34·35번.
 *
 * 사용: pnpm --filter @restaurant-map/db sem-pool e5-small     (모델마다 따로: e5-small, e5-base, bge-m3)
 *       모델마다 새 프로그램으로 돌리는 이유: 메모리(RSS)를 다른 모델의 흔적 없이 깨끗하게 재려고
 *
 * 1. 풀링 (TREC 식): 974곳 전부를 질문마다 사람이 판정할 수는 없다.
 *    질문마다 각 모델이 뽑은 상위 TOP 곳만 모아서 → 사람이 그것만 판정한다 (scripts/sem_label_server.py)
 *    → 모델마다 상위 TOP 곳 중 맞은 비율을 잰다 (scripts/sem_score.py).
 *    새 모델을 돌리면 그 모델이 새로 뽑은 쌍만 추가로 판정하면 된다.
 * 2. 측정: 모델 불러오기 시간, 소개글 임베딩 속도, 검색어 하나 응답 시간, 메모리.
 *    배포하면 이 모델이 서버 안에서 돈다 → 메모리가 곧 서버 크기(비용)다.
 *
 * 비교를 공정하게: 모든 모델이 같은 문서(store_texts 의 글자)와 같은 질문을 쓰고, 같은 방법(코사인)으로 순위를 낸다.
 * 문서 벡터는 DB 가 아니라 메모리에서 계산한다 (974곳이라 전부 비교해도 순식간). 다시 돌릴 때를 위해 파일에 저장해 둔다.
 *
 * 읽는 것: data/labels/sem_queries.csv   (query_id, kind, query)
 * 쓰는 것: data/labels/sem_pool.csv      (query_id, system, rank, store_id)  — 이 모델 줄만 바꿔 쓴다
 *          data/labels/sem_docs.csv      (store_id, name, sgg, text)        — 판정 화면에 보여줄 소개글
 *          results/sem_bench.json        모델별 속도·메모리
 */
import { existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import pg from "pg";
import { embedPassages, embedQuery, type ModelKey, MODELS } from "@restaurant-map/embed";

const ROOT = join(import.meta.dirname, "..", "..", "..");
const LABELS = join(ROOT, "data", "labels");
const DATABASE_URL = process.env.DATABASE_URL ?? "postgres://map:map@127.0.0.1:5432/restaurant_map";
const TOP = 5;
const BATCH = 16;

/** CSV 한 줄 → 칸들. 큰따옴표 안의 쉼표·큰따옴표("")도 처리한다 */
function parseLine(line: string): string[] {
  const out: string[] = [];
  let cur = "", quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cur += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}
const readCsv = async (path: string) =>
  existsSync(path) ? (await readFile(path, "utf8")).trim().split("\n").slice(1).filter(Boolean).map(parseLine) : [];

/** 칸 → CSV 글자 (쉼표·큰따옴표·줄바꿈이 있으면 큰따옴표로 감싼다) */
const cell = (v: string | number) => {
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
};
const toCsv = (header: string[], rows: (string | number)[][]) =>
  [header, ...rows].map((r) => r.map(cell).join(",")).join("\n") + "\n";

const rssMb = () => Math.round(process.memoryUsage().rss / 1e6);
const dot = (a: number[], b: number[]) => a.reduce((s, x, i) => s + x * b[i], 0);   // 길이 1 벡터끼리는 내적 = 코사인

async function main() {
  const key = process.argv[2] as ModelKey;
  if (!(key in MODELS)) throw new Error(`모델을 골라야 한다: ${Object.keys(MODELS).join(" | ")}`);

  const queries = (await readCsv(join(LABELS, "sem_queries.csv"))).map(([id, kind, query]) => ({ id, kind, query }));
  const db = new pg.Client({ connectionString: DATABASE_URL });
  await db.connect();
  const docs = (await db.query<{ store_id: string; text: string }>("SELECT store_id, text FROM store_texts ORDER BY store_id")).rows;

  // 문서 벡터: 저장해 둔 게 있고 문서가 그대로면 다시 쓴다 (bge-m3 는 974개에 몇 분 걸린다)
  const cachePath = join(ROOT, "data", "processed", `vectors_${key}.json`);
  const signature = docs.map((d) => `${d.store_id}:${d.text.length}`).join("|");
  // 서비스 상황을 먼저 잰다: 모델 불러오기 + 검색어 20개. 배포한 서버가 하는 일이 딱 이것이다
  const baseRss = rssMb();
  const t0 = Date.now();
  await embedQuery("준비", key);                       // 모델 불러오기 (첫 호출)
  const loadMs = Date.now() - t0;
  const queryVecs: number[][] = [];
  const queryMs: number[] = [];
  for (const q of queries) {
    const t = performance.now();
    queryVecs.push(await embedQuery(q.query, key));
    queryMs.push(performance.now() - t);
  }
  const serveRss = rssMb();

  // 문서 벡터 (배치 작업 — 배포 서버가 아니라 데이터 갱신 때 한 번 하는 일).
  // 저장해 둔 게 있고 문서가 그대로면 다시 쓴다 (bge-m3 는 974개에 몇 분 걸린다)
  let vectors: number[][];
  let docsPerSec: number | null = null;
  const cache = existsSync(cachePath) ? JSON.parse(await readFile(cachePath, "utf8")) : null;
  if (cache?.signature === signature) {
    vectors = cache.vectors;
  } else {
    vectors = [];
    const t1 = Date.now();
    for (let i = 0; i < docs.length; i += BATCH) {
      vectors.push(...await embedPassages(docs.slice(i, i + BATCH).map((d) => d.text), key));
      process.stdout.write(`\r  문서 임베딩 ${Math.min(i + BATCH, docs.length)} / ${docs.length}`);
    }
    docsPerSec = docs.length / ((Date.now() - t1) / 1000);
    console.log();
    await writeFile(cachePath, JSON.stringify({ signature, vectors }));
  }
  const batchRss = rssMb();

  // 질문마다 상위 TOP 곳 (질문 벡터와 974곳 문서 벡터의 코사인)
  const rows: (string | number)[][] = [];
  queries.forEach((q, qi) => {
    const top = docs.map((d, i) => ({ id: d.store_id, s: dot(queryVecs[qi], vectors[i]) })).sort((a, b) => b.s - a.s).slice(0, TOP);
    top.forEach((d, i) => rows.push([q.id, key, i + 1, d.id]));
  });

  // sem_pool.csv: 이 모델 줄만 새로 쓰고 다른 모델 줄은 그대로 둔다
  const poolPath = join(LABELS, "sem_pool.csv");
  const others = (await readCsv(poolPath)).filter((r) => r[1] !== key);
  const pool = [...others, ...rows];
  await writeFile(poolPath, toCsv(["query_id", "system", "rank", "store_id"], pool));
  // 판정 화면용 소개글: 모든 모델이 뽑은 가게
  const ids = [...new Set(pool.map((r) => String(r[3])))];
  const meta = await db.query(
    "SELECT t.store_id, s.name, s.sgg, t.text FROM store_texts t JOIN stores s USING (store_id) WHERE t.store_id = ANY($1)", [ids]);
  await writeFile(join(LABELS, "sem_docs.csv"), toCsv(["store_id", "name", "sgg", "text"], meta.rows.map((r) => [r.store_id, r.name, r.sgg ?? "", r.text])));
  await db.end();

  // 속도·메모리 기록 (모델별로 합쳐 둔다)
  const benchPath = join(ROOT, "results", "sem_bench.json");
  const bench = existsSync(benchPath) ? JSON.parse(await readFile(benchPath, "utf8")) : {};
  const sorted = [...queryMs].sort((a, b) => a - b);
  bench[key] = {
    model: MODELS[key].id, dim: MODELS[key].dim, fileMb: MODELS[key].sizeMb,
    loadMs, docsPerSec: docsPerSec ?? bench[key]?.docsPerSec ?? null,
    queryMsMedian: Number(sorted[Math.floor(sorted.length / 2)].toFixed(1)),
    rssStartMb: baseRss,          // 모델 불러오기 전 (Node + DB 연결)
    rssServeMb: serveRss,         // 모델 + 검색어 처리 = 배포 서버가 쓰는 메모리
    rssBatchMb: docsPerSec ? batchRss : bench[key]?.rssBatchMb ?? null,   // 문서 배치 임베딩 중 최대치 (데이터 갱신 때만)
    measuredAt: new Date().toISOString().slice(0, 10),
  };
  await writeFile(benchPath, JSON.stringify(bench, null, 2) + "\n");
  const pairs = new Set(pool.map((r) => `${r[0]}|${r[3]}`)).size;
  console.log(`${key}: 불러오기 ${loadMs}ms · 검색어 중앙값 ${bench[key].queryMsMedian}ms · 메모리 시작 ${baseRss} → 서비스 ${serveRss} → 배치 ${batchRss}MB`
    + (docsPerSec ? ` · 문서 ${docsPerSec.toFixed(0)}개/초` : " · 문서 벡터는 저장본 사용"));
  console.log(`판정할 (질문, 가게) 쌍은 모든 모델을 합쳐 ${pairs}개`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

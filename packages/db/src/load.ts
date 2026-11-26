/**
 * CSV 6개(파이썬 결과물) → Postgres 서비스용 표. 결정 일지 12·20·21·25·33번.
 *
 * 사용: pnpm db:load        (먼저 docker compose up -d, 파이썬 match_all.py → match_stage2.py → prep_tour_detail.py 까지 돌려둘 것)
 *       pnpm db:embed       (그다음 의미 검색 벡터 채우기. db:load 가 표를 새로 만들므로 매번 다시 돌린다)
 *
 * 흐름 (전부 트랜잭션 하나 — 중간에 실패하면 전부 취소되고 기존 DB가 그대로 남는다):
 *   1. schema.sql     서비스용 표를 지우고 새로 만든다
 *   2. staging        CSV 를 열 이름 그대로, 전부 글자(text)로 임시 표에 COPY 한다
 *   3. transform.sql  거르기·형 변환·체크 열 계산을 SQL 로 한다
 *   4. 검사           staging 과 결과의 건수가 맞는지 확인한다. 안 맞으면 취소
 *
 * CSV 를 TS 에서 한 줄씩 읽지 않는 이유: 상가가 277만 행이라 객체로 만들면 느리고 메모리를 많이 쓴다.
 * Postgres 의 COPY 는 CSV 를 그대로 받아들이므로, TS 는 파일을 DB로 흘려보내기만 한다.
 */
import { createReadStream } from "node:fs";
import { readFile } from "node:fs/promises";
import { createInterface } from "node:readline";
import { join } from "node:path";
import { pipeline } from "node:stream/promises";
import pg from "pg";
import { from as copyFrom } from "pg-copy-streams";

const ROOT = join(import.meta.dirname, "..", "..", "..");
const PROCESSED = join(ROOT, "data", "processed");
const SQL_DIR = join(import.meta.dirname, "..", "sql");
// compose.yaml 의 로컬 DB. 다른 DB에 넣으려면 DATABASE_URL 환경변수로 바꾼다
const DATABASE_URL = process.env.DATABASE_URL ?? "postgres://map:map@127.0.0.1:5432/restaurant_map";

// staging 표 이름 → CSV 파일
const STAGING = {
  sangga: "sangga.csv",
  certs: "certs.csv",
  matches: "matches.csv",
  cert_store: "cert_store.csv",
  new_stores: "new_stores.csv",
  tour_detail: "tour_detail.csv",
} as const;

/** CSV 첫 줄(열 이름)만 읽는다. staging 표의 열을 CSV 에 맞춰 만들려고. */
async function readHeader(path: string): Promise<string[]> {
  const lines = createInterface({ input: createReadStream(path, "utf8") });
  for await (const line of lines) {
    lines.close();
    return line.split(",");
  }
  throw new Error(`빈 파일: ${path}`);
}

/** CSV 하나를 staging 표로 옮긴다. 열은 전부 text — 형 변환은 transform.sql 에서 한 곳에 모아 한다. */
async function copyToStaging(db: pg.ClientBase, table: string, file: string) {
  const path = join(PROCESSED, file);
  const cols = await readHeader(path);
  await db.query(`CREATE TABLE staging.${table} (${cols.map((c) => `"${c}" text`).join(", ")})`);
  const started = Date.now();
  await pipeline(
    createReadStream(path),
    db.query(copyFrom(`COPY staging.${table} FROM STDIN WITH (FORMAT csv, HEADER true)`)),
  );
  console.log(`  staging.${table.padEnd(8)} ${((Date.now() - started) / 1000).toFixed(1)}초`);
}

/** 숫자 하나를 돌려주는 쿼리용 */
async function count(db: pg.ClientBase, sql: string): Promise<number> {
  const { rows } = await db.query(sql);
  return Number(Object.values(rows[0])[0]);
}

async function main() {
  const db = new pg.Client({ connectionString: DATABASE_URL });
  await db.connect();
  try {
    await db.query("BEGIN");
    console.log("1. 표 만들기");
    await db.query(await readFile(join(SQL_DIR, "schema.sql"), "utf8"));

    console.log("2. CSV → staging");
    await db.query("DROP SCHEMA IF EXISTS staging CASCADE; CREATE SCHEMA staging");
    for (const [table, file] of Object.entries(STAGING)) {
      await copyToStaging(db, table, file);
    }

    // transform 이 staging 을 지우기 전에 "있어야 할 건수"를 재 둔다
    const expected = {
      certs: await count(db, "SELECT count(*) FROM staging.certs"),
      stage1: await count(db, "SELECT count(*) FROM staging.cert_store WHERE stage = '1'"),
      certStores: await count(db, "SELECT count(DISTINCT store_id) FROM staging.cert_store"),
      newStores: await count(db, "SELECT count(*) FROM staging.new_stores"),
    };

    console.log("3. 변환 (거르기·형 변환·체크 열 계산·색인)");
    const started = Date.now();
    await db.query(await readFile(join(SQL_DIR, "transform.sql"), "utf8"));
    console.log(`  ${((Date.now() - started) / 1000).toFixed(1)}초`);

    console.log("4. 검사");
    const actual = {
      certs: await count(db, "SELECT count(*) FROM certs"),
      stage1: await count(db, "SELECT count(*) FROM certs WHERE match_stage = 1"),
      certStores: await count(db, "SELECT count(*) FROM stores WHERE cert_count > 0"),
      newStores: await count(db, "SELECT count(*) FROM stores WHERE origin = 'cert'"),
    };
    for (const key of Object.keys(expected) as (keyof typeof expected)[]) {
      const ok = expected[key] === actual[key];
      console.log(`  ${ok ? "✓" : "✗"} ${key}: CSV ${expected[key].toLocaleString()} / DB ${actual[key].toLocaleString()}`);
      if (!ok) throw new Error(`${key} 건수가 다르다 — 적재를 취소한다`);
    }

    await db.query("COMMIT");
    await printSummary(db);
  } catch (err) {
    await db.query("ROLLBACK");
    throw err;
  } finally {
    await db.end();
  }
}

/** 적재 결과 요약: 가게 수, 인증 종류별 가게 수 */
async function printSummary(db: pg.ClientBase) {
  const { rows } = await db.query(`
    SELECT count(*)                                AS "가게 전체",
           count(*) FILTER (WHERE is_food)         AS "음식점",
           count(*) FILTER (WHERE cert_count > 0)  AS "인증 붙은 가게",
           count(*) FILTER (WHERE origin = 'cert')  AS "상가에 없는 가게",
           count(*) FILTER (WHERE lat IS NULL)      AS "좌표 없음",
           count(*) FILTER (WHERE cert_count > 0 AND NOT is_food) AS "인증 붙은 비음식점",
           count(*) FILTER (WHERE mobum)      AS "모범음식점",
           count(*) FILTER (WHERE good_price) AS "착한가격업소",
           count(*) FILTER (WHERE baengnyeon) AS "백년가게",
           count(*) FILTER (WHERE tour)       AS "관광공사",
           count(*) FILTER (WHERE hygiene)    AS "식품안심업소",
           count(*) FILTER (WHERE ansim)      AS "안심식당",
           count(*) FILTER (WHERE lx)         AS "LX공사맛집"
    FROM stores`);
  console.log("\n적재 완료");
  for (const [k, v] of Object.entries(rows[0])) console.log(`  ${k.padEnd(12)} ${Number(v).toLocaleString()}`);

  const dist = await db.query(
    "SELECT cert_count, count(*) AS n FROM stores WHERE cert_count > 0 GROUP BY 1 ORDER BY 1",
  );
  console.log("\n  인증 개수별 가게 수: " + dist.rows.map((r) => `${r.cert_count}개 ${Number(r.n).toLocaleString()}`).join(" / "));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

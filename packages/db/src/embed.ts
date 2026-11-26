/**
 * 의미 검색 벡터 채우기: store_texts 의 글자 → 임베딩 → embedding 열. 결정 일지 33번.
 *
 * 사용: pnpm db:embed     (pnpm db:load 다음에. load 가 표를 새로 만들어 벡터가 지워지므로 매번 다시 돌린다)
 *
 * 하는 일:
 *   1. 아직 벡터가 없는 문서를 BATCH 개씩 꺼내 임베딩한다 (packages/embed — 서버 검색과 같은 모델)
 *   2. 다 채우면 HNSW 색인을 만든다. 색인이 없으면 검색할 때마다 모든 벡터와 거리를 재야 한다
 */
import pg from "pg";
import { EMBED_MODEL, embedPassages, toVectorLiteral } from "@restaurant-map/embed";

const DATABASE_URL = process.env.DATABASE_URL ?? "postgres://map:map@127.0.0.1:5432/restaurant_map";
const BATCH = 32;          // 한 번에 임베딩할 문서 수. 너무 크면 메모리를 많이 쓰고, 너무 작으면 느리다

async function main() {
  const db = new pg.Client({ connectionString: DATABASE_URL });
  await db.connect();
  try {
    const { rows } = await db.query<{ store_id: string; text: string }>(
      "SELECT store_id, text FROM store_texts WHERE embedding IS NULL ORDER BY store_id",
    );
    console.log(`문서 ${rows.length.toLocaleString()}개 임베딩 (${EMBED_MODEL})`);
    const started = Date.now();
    for (let i = 0; i < rows.length; i += BATCH) {
      const batch = rows.slice(i, i + BATCH);
      const vectors = await embedPassages(batch.map((r) => r.text));
      // 한 번에 여러 행을 고친다: unnest 로 (번호 목록, 벡터 목록)을 표처럼 펼쳐 붙인다
      await db.query(
        `UPDATE store_texts t SET embedding = v.e::vector
         FROM unnest($1::text[], $2::text[]) AS v(id, e) WHERE t.store_id = v.id`,
        [batch.map((r) => r.store_id), vectors.map(toVectorLiteral)],
      );
      process.stdout.write(`\r  ${Math.min(i + BATCH, rows.length).toLocaleString()} / ${rows.length.toLocaleString()}`);
    }
    console.log(`\n  ${((Date.now() - started) / 1000).toFixed(1)}초`);

    // 코사인 거리용 HNSW 색인. 문서가 수만 개로 늘어도 가까운 벡터를 빠르게 찾는다
    await db.query("DROP INDEX IF EXISTS store_texts_embedding_idx");
    await db.query("CREATE INDEX store_texts_embedding_idx ON store_texts USING hnsw (embedding vector_cosine_ops)");
    await db.query("ANALYZE store_texts");
    const n = await db.query("SELECT count(*)::int AS n FROM store_texts WHERE embedding IS NOT NULL");
    console.log(`벡터 있는 문서 ${n.rows[0].n.toLocaleString()}개, 색인 완료`);
  } finally {
    await db.end();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

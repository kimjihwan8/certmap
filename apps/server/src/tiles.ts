/**
 * 벡터 타일: 지도의 타일 한 장(z/x/y)에 들어가는 인증 가게를 PostGIS 가 압축(MVT)해서 돌려준다. 결정 일지 27번.
 *
 * 확대 수준에 따라 두 가지로 준다 (전국이 보일 때 가게를 하나하나 주면 타일 한 장이 2.6MB 가 된다):
 *   z ≤ GRID_MAX_ZOOM  'clusters' 층: 타일을 8×8 격자로 나눠 칸마다 점 하나 + 가게 수(n)
 *   z >  GRID_MAX_ZOOM  'stores' 층:   가게 점. 같은 좌표(같은 건물)의 가게는 점 하나 + 개수(n)
 *
 * 측정 (대전역 타일, results/tiles.txt 참고):
 *   z7  하나하나 2.6MB·106ms → 격자 11KB·32ms
 *   z12 하나하나 103KB → 아직 무거워서 z12 까지 격자, z13 부터 하나하나
 */
import { pool } from "./db.js";

export const GRID_MAX_ZOOM = 12;
// 타일 한 변을 몇 칸으로 나눌지. 512px 타일이면 칸당 64px.
// 처음엔 32칸(16px)이었는데, 원 지름(최대 48px)보다 칸이 작아 z8 에서 원 1,510개가 겹쳐 읽을 수 없었다.
const GRID_CELLS = 8;
const WORLD_ORIGIN = -20037508.342789244;    // 웹 메르카토르 좌표계의 왼쪽 아래 끝

// 가게 점. ST_AsMVTGeom 이 좌표를 타일 안 0~4096 정수 격자로 바꾸고, 타일 밖은 잘라낸다.
// buffer 64: 타일 경계에 걸친 점의 원이 잘려 보이지 않도록 경계 바깥 조금까지 포함한다.
//
// 같은 좌표의 가게는 점 하나로 묶는다 (결정 29번). 상가 좌표는 건물 단위라 인증 가게의 27%가 다른 가게와 좌표가 같다.
//   DISTINCT ON (좌표): 좌표마다 한 줄만 남긴다. 실린 목록이 많은 가게가 대표가 된다 (LX 를 앞세우지 않는다, 결정 32번)
//   count(*) OVER (좌표): 그 좌표에 겹친 가게 수 (n). 화면은 n > 1 이면 '대표 외 n-1곳' 으로 보여준다
const STORES_SQL = `
  SELECT ST_AsMVT(t, 'stores', 4096, 'geom') AS tile FROM (
    SELECT ST_AsMVTGeom(g.geom_3857, b.env, 4096, 64, true) AS geom,
           g.store_id AS id, g.name, g.cert_count, g.lx, g.n
    FROM (
      SELECT DISTINCT ON (s.geom_3857) s.geom_3857, s.store_id, s.name, s.cert_count, s.lx,
             (count(*) OVER (PARTITION BY s.geom_3857))::int AS n
      FROM stores s, (SELECT ST_TileEnvelope($1, $2, $3) AS env) e
      WHERE s.cert_count > 0 AND s.geom_3857 && ST_Expand(e.env, (ST_XMax(e.env) - ST_XMin(e.env)) * 64 / 4096)
      ORDER BY s.geom_3857, s.cert_count DESC, s.store_id
    ) g, (SELECT ST_TileEnvelope($1, $2, $3) AS env) b
  ) t`;

// 격자로 묶기. ST_SnapToGrid 로 점을 칸에 떨어뜨리고, 같은 칸끼리 GROUP BY 해서 가운데 점과 개수를 낸다.
// 격자 원점을 세계 끝(WORLD_ORIGIN)에 맞추면 칸 경계가 타일 경계와 딱 맞아, 한 칸이 두 타일에 걸치지 않는다.
const GRID_SQL = `
  SELECT ST_AsMVT(t, 'clusters', 4096, 'geom') AS tile FROM (
    SELECT ST_AsMVTGeom(ST_Centroid(ST_Collect(s.geom_3857)), b.env, 4096, 0, true) AS geom,
           count(*)::int AS n
    FROM stores s, (SELECT ST_TileEnvelope($1, $2, $3) AS env) b
    WHERE s.cert_count > 0 AND s.geom_3857 && b.env
    GROUP BY b.env, ST_SnapToGrid(s.geom_3857, ${WORLD_ORIGIN}, ${WORLD_ORIGIN},
                                  (ST_XMax(b.env) - ST_XMin(b.env)) / ${GRID_CELLS},
                                  (ST_XMax(b.env) - ST_XMin(b.env)) / ${GRID_CELLS})
  ) t`;

/** 타일 한 장(MVT 바이너리). 그 타일에 가게가 없으면 빈 Buffer. */
export async function getTile(z: number, x: number, y: number): Promise<Buffer> {
  const sql = z <= GRID_MAX_ZOOM ? GRID_SQL : STORES_SQL;
  const { rows } = await pool.query<{ tile: Buffer }>(sql, [z, x, y]);
  return rows[0].tile;
}

/** z/x/y 가 실제로 있는 타일 번호인지. 아니면 PostGIS 가 오류를 내므로 미리 거른다. */
export function isValidTile(z: number, x: number, y: number): boolean {
  const n = 2 ** z;
  return [z, x, y].every(Number.isInteger) && z >= 0 && z <= 22 && x >= 0 && x < n && y >= 0 && y < n;
}

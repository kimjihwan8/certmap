/** Postgres 연결. 서버 전체가 연결 묶음(pool) 하나를 같이 쓴다. */
import pg from "pg";

// 연결을 요청마다 새로 맺으면 느리다. pool 은 열어 둔 연결 몇 개를 돌려 쓴다.
export const pool = new pg.Pool({
  // compose.yaml 의 로컬 DB. 배포할 때는 DATABASE_URL 환경변수로 바꾼다
  connectionString: process.env.DATABASE_URL ?? "postgres://map:map@127.0.0.1:5432/restaurant_map",
  max: 10,
});

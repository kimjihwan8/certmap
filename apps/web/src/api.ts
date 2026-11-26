/**
 * API 클라이언트. 서버(apps/server)의 라우트 타입(AppType)을 그대로 가져다 쓴다 (Hono RPC, 결정 일지 27번).
 * 서버에서 주소나 응답 모양을 바꾸면 이 파일을 쓰는 화면 코드에서 타입 오류가 난다 → 서버·화면이 어긋날 수 없다.
 */
import { hc } from "hono/client";
import type { AppType } from "@restaurant-map/server";

const client = hc<AppType>("/");

/** 가게 상세. 없는 가게면 null. */
export async function fetchStore(id: string) {
  const res = await client.api.stores[":id"].$get({ param: { id } });
  if (!res.ok) {
    if (res.status === 404) return null;
    // 서버 타입에는 200·404 만 있지만, 서버가 죽었을 때(500 등)도 여기로 온다
    throw new Error("가게 정보를 못 불러왔어요");
  }
  return res.json();
}

export type StoreDetail = NonNullable<Awaited<ReturnType<typeof fetchStore>>>;

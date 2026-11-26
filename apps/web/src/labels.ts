/** 화면 여러 곳에서 같이 쓰는 표시 문구와 색 */
import type { CertFilter } from "./api";

// 인증 원본 → 화면 이름과 색. LX·관광공사는 인증이 아니므로 출처를 그대로 적는다 (결정 10·24번).
// 색은 출처를 구별하려는 것일 뿐, 어느 쪽이 더 좋다는 뜻이 아니다 (결정 32번: LX 를 앞세우지 않는다)
export const SOURCES: Record<string, { label: string; short: string; color: string }> = {
  모범음식점: { label: "모범음식점", short: "모범", color: "#2563eb" },
  착한가격업소: { label: "착한가격업소", short: "착한가격", color: "#059669" },
  백년가게: { label: "백년가게", short: "백년가게", color: "#7c3aed" },
  식품안심업소: { label: "식품안심업소", short: "식품안심", color: "#0891b2" },
  안심식당: { label: "안심식당", short: "안심식당", color: "#0d9488" },
  관광공사: { label: "관광공사 관광정보", short: "관광정보", color: "#b45309" },
  LX공사맛집: { label: "LX 직원 추천", short: "LX 추천", color: "#be185d" },
};

// 인증 칩: 서버 find.ts 의 칩 이름과 같다 (타입이 서버에서 오므로 이름이 어긋나면 타입 검사가 잡는다).
// sources = 이 칩을 만족하는 인증 원본 (목록의 배지를 진하게 칠할 때 쓴다)
export const CERT_CHIPS: { key: CertFilter; label: string; sources: string[] }[] = [
  { key: "good_price", label: "착한가격", sources: ["착한가격업소"] },
  { key: "baengnyeon", label: "백년가게", sources: ["백년가게"] },
  { key: "mobum", label: "모범음식점", sources: ["모범음식점"] },
  { key: "hygiene", label: "위생", sources: ["식품안심업소", "안심식당"] },
  { key: "lx", label: "LX 추천", sources: ["LX공사맛집"] },
  { key: "tour", label: "관광정보", sources: ["관광공사"] },
];

export function formatDistance(m: number): string {
  return m < 1000 ? `${m}m` : `${(m / 1000).toFixed(m < 10000 ? 1 : 0)}km`;
}

/**
 * 조건 검색 훅. 칩(인증 종류·업종)이나 검색 기준점이 바뀌면 다시 찾는다. 결정 일지 30·32번.
 * 칩이 하나도 없으면 '이 근처 인증 가게'(실린 목록 많은 순)를 가져온다 — 처음 화면과 "맛집" 검색이 이걸 쓴다.
 * 칩을 여러 개 빠르게 눌러도 요청이 몰리지 않게, 마지막 변경 뒤 DEBOUNCE_MS 가 지나면 한 번만 묻는다.
 */
import { useEffect, useRef, useState } from "react";
import { type CertFilter, findStores, type FindResult } from "./api";

const DEBOUNCE_MS = 250;

export function useFind(p: {
  enabled: boolean;                            // 이름 검색 중에는 끈다
  certs: CertFilter[];
  cats: string[];
  q: string;                                   // 검색창 글자. 있으면 이름으로도 거른다
  center: { lat: number; lon: number };        // 검색 기준점 (지도를 옮기면 바뀐다)
}) {
  const [result, setResult] = useState<FindResult | null>(null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);
  // 배열은 렌더링마다 새로 만들어지므로, 내용이 같으면 다시 찾지 않도록 글자로 바꿔 비교한다
  const key = JSON.stringify([p.enabled, p.certs, p.cats, p.q, p.center]);

  useEffect(() => {
    if (!p.enabled) {
      latest.current++;
      setLoading(false);
      return;
    }
    setLoading(true);
    const timer = setTimeout(async () => {
      const id = ++latest.current;
      try {
        const r = await findStores({ ...p.center, certs: p.certs, cats: p.cats, q: p.q });
        if (id === latest.current) setResult(r);
      } catch {
        if (id === latest.current) setResult(null);
      } finally {
        if (id === latest.current) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // key 가 p 의 내용 전체를 담고 있다
  }, [key]);

  return { result, loading };
}

/**
 * 상호 검색 훅 (가게 + 장소). 결정 일지 28·30번.
 *
 * 글자를 칠 때마다 서버에 묻지 않고, 멈춘 뒤 DEBOUNCE_MS 가 지나면 한 번 묻는다 ('성심당'을 치는 동안 요청 1번).
 * 늦게 도착한 옛 응답이 새 결과를 덮지 않도록 요청 번호를 센다.
 */
import { useEffect, useRef, useState } from "react";
import { type PlaceHit, searchStores, type SearchHit } from "./api";

const DEBOUNCE_MS = 200;

export function useStoreSearch(query: string, getCenter: () => { lat: number; lon: number }) {
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [places, setPlaces] = useState<PlaceHit[]>([]);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  useEffect(() => {
    const text = query.trim();
    if (!text) {
      latest.current++;          // 진행 중이던 요청의 응답은 버린다
      setHits([]);
      setPlaces([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const timer = setTimeout(async () => {
      const id = ++latest.current;
      const { lat, lon } = getCenter();      // 검색하는 순간의 지도 중심에서 가까운 순
      try {
        const result = await searchStores(text, lat, lon);
        if (id === latest.current) {
          setHits(result.stores);
          setPlaces(result.places);
        }
      } catch {
        if (id === latest.current) {
          setHits([]);
          setPlaces([]);
        }
      } finally {
        if (id === latest.current) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, getCenter]);

  return { hits, places, loading };
}

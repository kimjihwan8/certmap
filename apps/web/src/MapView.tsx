/**
 * 지도. MapLibre 가 우리 서버의 벡터 타일(/api/tiles)을 GPU 로 그린다. 결정 일지 27번.
 *
 * 층 두 개 (서버가 확대 수준에 따라 다른 층을 준다, apps/server/src/tiles.ts):
 *   clusters  z12 까지. 격자 칸마다 원 하나 + 가게 수. 누르면 그 자리로 확대
 *   stores    z13 부터. 가게 하나하나. 누르면 상세 패널
 */
import { useEffect, useRef } from "react";
import { Map as MapLibre, NavigationControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// 서버 tiles.ts 의 GRID_MAX_ZOOM 과 맞춘다: 여기까지는 묶음, 다음 수준부터 가게 하나하나
const GRID_MAX_ZOOM = 12;
// 처음 보여줄 곳: 대전역. 지금까지 모든 예시가 대전역이라서
const START = { center: [127.4342, 36.3324] as [number, number], zoom: 14 };
// 바탕 지도: OpenFreeMap 의 positron (OSM 기반, 무료·키 없음). 흐린 색이라 우리 점이 잘 보인다
const BASEMAP = "https://tiles.openfreemap.org/styles/positron";

export function MapView({ onSelect }: { onSelect: (storeId: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  // onSelect 가 렌더링마다 바뀌어도 지도를 다시 만들지 않도록, 최신 함수를 ref 에 담아 둔다
  const select = useRef(onSelect);
  select.current = onSelect;

  useEffect(() => {
    const map = new MapLibre({ container: container.current!, style: BASEMAP, ...START });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    // 개발 중에만: 브라우저 자동 테스트(스크린샷·클릭 확인)가 지도에 접근할 수 있게 열어 둔다. 배포 빌드에는 안 들어간다
    if (import.meta.env.DEV) (window as unknown as { map: MapLibre }).map = map;

    map.on("load", () => {
      map.addSource("certs", {
        type: "vector",
        tiles: [`${location.origin}/api/tiles/{z}/{x}/{y}`],
        maxzoom: 16,     // z16 보다 더 확대하면 z16 타일을 늘려 쓴다 (점 위치는 충분히 정확하다)
      });

      // 묶음: 가게 수가 많을수록 큰 원
      map.addLayer({
        id: "clusters", type: "circle", source: "certs", "source-layer": "clusters",
        maxzoom: GRID_MAX_ZOOM + 1,
        paint: {
          "circle-color": "#2f6fdf",
          "circle-opacity": 0.8,
          "circle-radius": ["step", ["get", "n"], 9, 10, 13, 100, 18, 1000, 24],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      map.addLayer({
        id: "cluster-count", type: "symbol", source: "certs", "source-layer": "clusters",
        maxzoom: GRID_MAX_ZOOM + 1,
        layout: { "text-field": ["to-string", ["get", "n"]], "text-size": 11, "text-font": ["Noto Sans Regular"] },
        paint: { "text-color": "#ffffff" },
      });

      // 가게: LX 추천은 주황, 나머지는 파랑. 인증이 많을수록 큰 원 (결정 10번 정렬 기준을 눈으로도 보이게)
      map.addLayer({
        id: "stores", type: "circle", source: "certs", "source-layer": "stores",
        minzoom: GRID_MAX_ZOOM + 1,
        paint: {
          "circle-color": ["case", ["get", "lx"], "#e8710a", "#2f6fdf"],
          "circle-radius": ["step", ["get", "cert_count"], 5, 2, 7, 3, 9],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      // 가게 이름은 많이 확대했을 때만 (z15 아래에서는 글자가 겹쳐 읽을 수 없다)
      map.addLayer({
        id: "store-names", type: "symbol", source: "certs", "source-layer": "stores",
        minzoom: 15,
        layout: {
          "text-field": ["get", "name"], "text-size": 12, "text-font": ["Noto Sans Regular"],
          "text-offset": [0, 1.1], "text-anchor": "top", "text-optional": true,
        },
        paint: { "text-color": "#1f2937", "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
      });
    });

    map.on("click", "stores", (e) => {
      const id = e.features?.[0]?.properties?.id;
      if (typeof id === "string") select.current(id);
    });
    map.on("click", "clusters", (e) => {
      map.easeTo({ center: e.lngLat, zoom: Math.min(map.getZoom() + 2, GRID_MAX_ZOOM + 1) });
    });
    for (const layer of ["stores", "clusters"]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    return () => map.remove();
  }, []);

  return <div ref={container} className="map" />;
}

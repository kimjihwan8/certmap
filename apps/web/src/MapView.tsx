/**
 * 지도. MapLibre 가 우리 서버의 벡터 타일(/api/tiles)을 GPU 로 그린다. 결정 일지 27·29·32번.
 *
 * 층:
 *   clusters   z12 까지. 격자 칸마다 원 하나 + 가게 수. 누르면 그 자리로 확대
 *   stores     z13 부터. 같은 건물(같은 좌표)의 가게는 점 하나 + 개수(n). 누르면 n=1 은 상세, n>1 은 건물 목록
 *              색 진하기 = 실린 공공 목록 수. LX 를 따로 칠하지 않는다 (결정 32번)
 *   results    사이드바 목록의 가게. 인증 없는 가게는 타일에 없어서 따로 찍고 이름도 단다
 *   highlight  목록에서 마우스를 올린 가게
 */
import { useEffect, useRef } from "react";
import { GeolocateControl, type GeoJSONSource, Map as MapLibre, Marker, NavigationControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// 서버 tiles.ts 의 GRID_MAX_ZOOM 과 맞춘다: 여기까지는 묶음, 다음 수준부터 가게 점
const GRID_MAX_ZOOM = 12;
// 처음 보여줄 곳: 대전역. 지금까지 모든 예시가 대전역이라서
const START = { center: [127.4342, 36.3324] as [number, number], zoom: 14 };
const FONT = ["Noto Sans Regular"];

// 시스템이 다크 모드면 바탕 지도도 어둡게 (사이드바만 어둡고 지도는 밝으면 따로 논다)
const DARK = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
const THEME = DARK
  ? { basemap: "https://tiles.openfreemap.org/styles/dark", dots: ["#7fb0ff", "#3d82f6", "#1d4ed8"], text: "#e5e7eb", halo: "#111827", ring: "#ffffff" }
  : { basemap: "https://tiles.openfreemap.org/styles/positron", dots: ["#93b8f5", "#3d7be0", "#1e3a8a"], text: "#1f2937", halo: "#ffffff", ring: "#ffffff" };

export interface MapResult {
  storeId: string;
  name: string;
  lat: number;
  lon: number;
  certified: boolean;
}

export function MapView({ onSelect, onReady, selected, results, highlight }: {
  onSelect: (storeId: string, n: number) => void;     // n = 그 점에 겹친 가게 수
  onReady: (map: MapLibre) => void;                   // 검색이 지도 중심을 읽을 수 있게 지도 객체를 넘긴다
  selected: { lat: number; lon: number; label: string } | null;   // 고른 가게. 그 자리로 이동하고 이름 붙은 핀을 띄운다
  results: MapResult[];
  highlight: { lat: number; lon: number } | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const markers = useRef<Marker[]>([]);
  // onSelect 가 렌더링마다 바뀌어도 지도를 다시 만들지 않도록, 최신 함수를 ref 에 담아 둔다
  const select = useRef(onSelect);
  select.current = onSelect;
  // 결과·강조도 최신 값을 ref 에 담는다. 지도가 다 뜨기 전에 값이 오면 load 때 다시 반영한다
  const latest = useRef({ results, highlight });
  latest.current = { results, highlight };

  function applyOverlays() {
    const map = mapRef.current;
    (map?.getSource("results") as GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: latest.current.results.map((r) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [r.lon, r.lat] },
        properties: { id: r.storeId, name: r.name, certified: r.certified },
      })),
    });
    const h = latest.current.highlight;
    (map?.getSource("highlight") as GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: h ? [{ type: "Feature", geometry: { type: "Point", coordinates: [h.lon, h.lat] }, properties: {} }] : [],
    });
  }

  useEffect(() => {
    // 지도 출처 표시는 접히는 ⓘ 버튼으로 (휴대폰에서 펼쳐 두면 지도 아래쪽을 크게 가린다)
    const map = new MapLibre({ container: container.current!, style: THEME.basemap, attributionControl: { compact: true }, ...START });
    mapRef.current = map;
    onReady(map);
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    // 내 위치: 누르면 지도가 내 위치로 가고, 목록도 그 자리 기준으로 다시 찾는다 (moveend)
    map.addControl(new GeolocateControl({ positionOptions: { enableHighAccuracy: false } }), "top-right");
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
          "circle-color": THEME.dots[1],
          "circle-opacity": 0.85,
          "circle-radius": ["step", ["get", "n"], 9, 10, 13, 100, 18, 1000, 24],
          "circle-stroke-color": THEME.ring,
          "circle-stroke-width": 1.5,
        },
      });
      map.addLayer({
        id: "cluster-count", type: "symbol", source: "certs", "source-layer": "clusters",
        maxzoom: GRID_MAX_ZOOM + 1,
        layout: { "text-field": ["to-string", ["get", "n"]], "text-size": 11, "text-font": FONT },
        paint: { "text-color": "#ffffff" },
      });

      // 가게 점: 실린 목록이 많을수록 진하고 크다. 같은 건물에 여러 곳(n>1)이면 원을 키우고 안에 개수
      map.addLayer({
        id: "stores", type: "circle", source: "certs", "source-layer": "stores",
        minzoom: GRID_MAX_ZOOM + 1,
        paint: {
          "circle-color": ["step", ["get", "cert_count"], THEME.dots[0], 2, THEME.dots[1], 3, THEME.dots[2]],
          "circle-radius": ["case", [">", ["get", "n"], 1], 10, ["step", ["get", "cert_count"], 5, 2, 6.5, 3, 8]],
          "circle-stroke-color": THEME.ring,
          "circle-stroke-width": 1.5,
        },
      });
      map.addLayer({
        id: "store-count", type: "symbol", source: "certs", "source-layer": "stores",
        minzoom: GRID_MAX_ZOOM + 1,
        filter: [">", ["get", "n"], 1],
        layout: { "text-field": ["to-string", ["get", "n"]], "text-size": 11, "text-font": FONT, "text-allow-overlap": true },
        paint: { "text-color": "#ffffff" },
      });
      // 가게 이름은 많이 확대했을 때만 (z15 아래에서는 글자가 겹쳐 읽을 수 없다). 묶음이면 '대표 외 n-1곳'
      map.addLayer({
        id: "store-names", type: "symbol", source: "certs", "source-layer": "stores",
        minzoom: 15,
        layout: {
          "text-field": ["case", [">", ["get", "n"], 1],
            ["concat", ["get", "name"], " 외 ", ["to-string", ["-", ["get", "n"], 1]], "곳"],
            ["get", "name"]],
          "text-size": 12, "text-font": FONT,
          "text-offset": [0, 1.2], "text-anchor": "top", "text-optional": true,
        },
        paint: { "text-color": THEME.text, "text-halo-color": THEME.halo, "text-halo-width": 1.5 },
      });

      // 목록의 가게: 빨간 테두리. 인증 가게는 위 층에 이미 이름이 있으니, 인증 없는 가게만 이름을 단다
      map.addSource("results", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "results", type: "circle", source: "results",
        paint: { "circle-color": "rgba(0,0,0,0)", "circle-radius": 8, "circle-stroke-color": "#e5484d", "circle-stroke-width": 2.5 },
      });
      map.addLayer({
        id: "result-names", type: "symbol", source: "results",
        filter: ["!", ["get", "certified"]],
        layout: { "text-field": ["get", "name"], "text-size": 12, "text-font": FONT, "text-offset": [0, 1.2], "text-anchor": "top" },
        paint: { "text-color": "#e5484d", "text-halo-color": THEME.halo, "text-halo-width": 1.5 },
      });
      // 목록에서 마우스를 올린 가게: 크게 깜빡이는 대신 굵은 테두리 하나 (움직임은 눈을 피곤하게 한다)
      map.addSource("highlight", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "highlight", type: "circle", source: "highlight",
        paint: { "circle-color": "rgba(229,72,77,0.18)", "circle-radius": 16, "circle-stroke-color": "#e5484d", "circle-stroke-width": 3 },
      });
      applyOverlays();
    });

    map.on("click", "stores", (e) => {
      const p = e.features?.[0]?.properties;
      if (p && typeof p.id === "string") select.current(p.id, Number(p.n ?? 1));
    });
    map.on("click", "results", (e) => {
      const id = e.features?.[0]?.properties?.id;
      if (typeof id === "string") select.current(id, 1);
    });
    map.on("click", "clusters", (e) => {
      map.easeTo({ center: e.lngLat, zoom: Math.min(map.getZoom() + 2, GRID_MAX_ZOOM + 1) });
    });
    for (const layer of ["stores", "clusters", "results"]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    return () => map.remove();
  }, []);   // 지도는 처음 한 번만 만든다 (onReady 는 App 에서 useCallback 으로 고정돼 있다)

  useEffect(applyOverlays, [results, highlight]);

  // 가게를 고르면 그 자리로 이동하고, 핀 아래에 그 가게 이름을 붙인다.
  // 이름이 꼭 필요한 이유:
  //   - 인증 없는 가게는 타일에 점·이름이 없다 (결정 27번: 지도에는 인증 가게만)
  //   - 상가 좌표는 건물 단위라, 같은 건물의 다른 가게 이름이 핀 자리에 보일 수 있다 (성심당 대전역점 ↔ 예산국수)
  useEffect(() => {
    const map = mapRef.current;
    markers.current.forEach((m) => m.remove());
    markers.current = [];
    if (!map || !selected) return;
    const at: [number, number] = [selected.lon, selected.lat];
    const label = document.createElement("div");
    label.className = "pin-label";
    label.textContent = selected.label;
    markers.current = [
      new Marker({ color: "#e5484d" }).setLngLat(at).addTo(map),
      new Marker({ element: label, anchor: "top", offset: [0, 6] }).setLngLat(at).addTo(map),
    ];
    map.flyTo({ center: at, zoom: Math.max(map.getZoom(), 16) });
  }, [selected]);

  return (
    <div className="map-wrap">
      <div ref={container} className="map" />
      <div className="legend" aria-label="범례">
        <span><i style={{ background: THEME.dots[0] }} />목록 1개</span>
        <span><i style={{ background: THEME.dots[1] }} />2개</span>
        <span><i style={{ background: THEME.dots[2] }} />3개 이상</span>
        <span><i className="n" style={{ background: THEME.dots[1] }}>3</i>같은 건물</span>
      </div>
    </div>
  );
}

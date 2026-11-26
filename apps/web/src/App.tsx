/**
 * 화면 전체: 왼쪽 사이드바(검색창 + 조건 칩 + 목록/상세) + 오른쪽 지도. 네이버 지도식 배치. 결정 일지 29·30·32번.
 *
 * 사이드바에 보이는 것 (위에 있을수록 우선):
 *   1. 가게 상세    가게를 골랐을 때. '← 목록'으로 돌아간다
 *   2. 건물 목록    묶음 점(같은 건물 여러 곳)을 누르거나, 상세에서 '같은 건물의 다른 인증 가게'를 눌렀을 때
 *   3. 이름 검색    검색창에 글자를 치는 동안 (칩이 없을 때). 장소(📍)가 맨 위
 *   4. 근처 목록    그 밖의 모든 경우. 칩이 있으면 조건을 많이 만족한 순, 없으면 실린 목록이 많은 순
 *                   처음 화면부터 이 목록이 떠서 사이드바가 비어 있지 않다
 *   엔터를 치면 검색어를 해석해(자연어 → 칩, 결정 31번) 칩을 켜고 장소로 옮긴다
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Map as MapLibre } from "maplibre-gl";
import {
  type BuildingStore, type CertFilter, fetchBuilding, fetchStore, parseQuery, type ParseResult, type PlaceHit, type StoreDetail,
} from "./api";
import { FilterChips } from "./FilterChips";
import { CERT_CHIPS, formatDistance } from "./labels";
import { MapView } from "./MapView";
import { type ListItem, StoreList } from "./StoreList";
import { StorePanel } from "./StorePanel";
import { useFind } from "./useFind";
import { useStoreSearch } from "./useStoreSearch";

const START_CENTER = { lat: 36.3324, lon: 127.4342 };   // 대전역 (MapView 의 START 와 같다)

export function App() {
  const [query, setQuery] = useState("");
  const [certs, setCerts] = useState<CertFilter[]>([]);
  const [cats, setCats] = useState<string[]>([]);
  const [store, setStore] = useState<StoreDetail | null>(null);
  const [building, setBuilding] = useState<BuildingStore[] | null>(null);
  const [active, setActive] = useState(0);           // 목록에서 가리킨 줄 (키보드)
  const [hover, setHover] = useState<number | null>(null);   // 목록에서 마우스를 올린 줄 → 지도에 강조
  const [error, setError] = useState<string | null>(null);
  const [center, setCenter] = useState(START_CENTER);   // 근처 목록 기준점 = 지도를 옮긴 뒤의 중심
  const [placeName, setPlaceName] = useState<string | null>(null);   // 장소를 골랐으면 그 이름 ('대전역 근처')
  const [parsed, setParsed] = useState<{ text: string; result: ParseResult } | null>(null);   // 마지막 자연어 해석
  const [navigated, setNavigated] = useState(false);   // 방향키로 목록을 골랐는지. 그때만 엔터 = 가게 열기
  const map = useRef<MapLibre | null>(null);

  // 상세·건물 목록을 보는 동안에는 지도가 그 가게로 날아가도 목록을 다시 찾지 않는다
  // (목록으로 돌아왔을 때 순서가 바뀌어 있으면 헷갈린다)
  const browsing = useRef(false);
  browsing.current = store !== null || building !== null;

  // 이름 검색은 검색하는 순간의 지도 중심에서 가까운 순
  const getCenter = useCallback(() => {
    const c = map.current?.getCenter();
    return c ? { lat: c.lat, lon: c.lng } : START_CENTER;
  }, []);
  const onReady = useCallback((m: MapLibre) => {
    map.current = m;
    m.on("moveend", (e) => {
      if (browsing.current) return;
      // 사용자가 직접 옮겼으면(originalEvent 가 있음) 더 이상 '대전역 근처'가 아니다
      if (e.originalEvent) setPlaceName(null);
      const c = m.getCenter();
      setCenter({ lat: c.lat, lon: c.lng });
    });
  }, []);

  const chipsOn = certs.length > 0 || cats.length > 0;
  const nameMode = query.trim() !== "" && !chipsOn;
  const { hits, places, loading: nameLoading } = useStoreSearch(nameMode ? query : "", getCenter);
  const find = useFind({ enabled: !nameMode, certs, cats, q: chipsOn ? query.trim() : "", center });

  // 실패해도 화면이 멈추지 않게, 불러오기는 전부 이 함수를 거친다
  async function load<T>(work: () => Promise<T>): Promise<T | undefined> {
    setError(null);
    try {
      return await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function openStore(id: string) {
    const s = await load(() => fetchStore(id));
    if (s !== undefined) {
      setStore(s);
      setHover(null);
    }
  }
  async function openBuilding(id: string) {
    const list = await load(() => fetchBuilding(id));
    if (list) {
      setBuilding(list);
      setStore(null);
      setActive(0);
    }
  }
  // 지도에서 점을 눌렀을 때: 혼자 있는 가게면 상세, 같은 건물에 여러 곳이면 건물 목록
  function onMapSelect(id: string, n: number) {
    if (n > 1) openBuilding(id);
    else openStore(id);
  }
  // 기준점은 고르는 즉시 바꾼다. 지도가 날아가 도착(moveend)할 때까지 기다리면 그동안 옛 자리의 결과가
  // '서울역 근처'라는 머리말 아래 보인다 (실제로 겪은 문제)
  function pickPlace(p: PlaceHit) {
    setQuery("");
    setPlaceName(p.name);
    setCenter({ lat: p.lat, lon: p.lon });
    map.current?.flyTo({ center: [p.lon, p.lat], zoom: 15 });
  }

  // 엔터: 검색어를 칩으로 바꿔 채운다. 가게는 언제나 DB 에서 나온다 (결정 9번)
  async function runParse(text: string) {
    const r = await load(() => parseQuery(text));
    if (!r) return;
    setParsed({ text, result: r });
    if (r.used.length === 0) return;      // 읽은 게 없으면 검색어를 그대로 둔다 (가게 이름일 수 있다)
    setCerts(r.certs);
    setCats(r.cats);
    setQuery("");                          // 검색어는 칩·장소로 옮겨졌다. 남겨 두면 이름 거르기로 또 쓰인다
    if (r.place) pickPlace(r.place);
  }

  function onQueryChange(q: string) {
    setQuery(q);
    setNavigated(false);
    setBuilding(null);     // 검색을 시작하면 건물 목록 대신 검색 결과를 보여준다
    setStore(null);
    setActive(0);
    if (q) setParsed(null);   // 새로 치기 시작하면 지난 해석 표시를 지운다
  }
  function clearAll() {
    setQuery("");
    setCerts([]);
    setCats([]);
    setParsed(null);
    setPlaceName(null);
  }
  // 칩을 바꾸면 결과 목록으로 돌아간다
  useEffect(() => {
    setStore(null);
    setBuilding(null);
    setActive(0);
  }, [certs, cats]);

  // 칩이 가리키는 인증 원본 (목록 배지를 진하게 칠할 것). 칩이 없으면 null
  const hitSources = certs.length ? CERT_CHIPS.filter((c) => certs.includes(c.key)).flatMap((c) => c.sources) : null;

  // 사이드바 목록 한 줄의 공통 모양: 건물 목록 > 이름 검색 > 근처 목록
  type Row = {
    storeId: string; name: string; branch: string | null; category: string | null; sgg: string | null;
    floor: string | null; distance?: number; lat: number; lon: number; sources: string[]; matched: string[];
  };
  const rows: Row[] = useMemo(() => {
    if (building) return building.map((b) => ({ ...b, sgg: null, lat: 0, lon: 0, matched: [] }));
    if (nameMode) return hits.map((h) => ({ ...h, floor: null, matched: [] }));
    return (find.result?.hits ?? []).map((h) => ({ ...h, floor: null }));
  }, [building, nameMode, hits, find.result]);
  const conditions = find.result?.conditions ?? 0;
  const items: ListItem[] = rows.map((r) => ({
    storeId: r.storeId, name: r.name, branch: r.branch, category: r.category,
    place: r.floor ? `${r.floor}층` : r.sgg, distance: r.distance, sources: r.sources,
    categoryHit: r.matched.includes("category"),
    score: !building && !nameMode && conditions > 1 ? { got: r.matched.length, of: conditions } : undefined,
  }));

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !(navigated && items.length)) {
      if (query.trim()) runParse(query.trim());
      e.preventDefault();
      return;
    }
    if (e.key === "Escape") {
      clearAll();
      return;
    }
    if (store || items.length === 0) return;
    if (e.key === "ArrowDown") setActive((a) => (a + 1) % items.length);
    else if (e.key === "ArrowUp") setActive((a) => (a - 1 + items.length) % items.length);
    else if (e.key === "Enter") openStore(items[active].storeId);
    else return;
    setNavigated(true);
    e.preventDefault();
  }

  // 지도: 목록의 가게를 찍고, 마우스를 올린 가게를 강조한다 (상세·건물 목록을 볼 때는 숨긴다)
  const mapResults = useMemo(
    () => (building || store ? [] : rows.map((r) => ({ storeId: r.storeId, name: r.name, lat: r.lat, lon: r.lon, certified: r.sources.length > 0 }))),
    [building, store, rows],
  );
  const hovered = hover !== null && !building && !store ? rows[hover] : undefined;
  const highlight = useMemo(() => (hovered ? { lat: hovered.lat, lon: hovered.lon } : null), [hovered]);
  // 같은 가게를 다시 그려도 지도가 또 날아가지 않도록, 가게가 바뀔 때만 새 객체를 만든다
  const selected = useMemo(
    () => (store ? { lat: store.lat, lon: store.lon, label: [store.name, store.branch].filter(Boolean).join(" ") } : null),
    [store],
  );

  // 근처 목록 머리말: 어디 기준 · 몇 곳 · (칩이 2개 이상이면) 모두 만족한 곳 수
  function nearbyHead(): { title: string; sub: string } {
    const r = find.result;
    const where = placeName ? `${placeName} 근처` : "이 근처";
    if (!r) return { title: find.loading ? "찾는 중…" : where, sub: "" };
    const range = `${formatDistance(r.radius)} 안`;
    if (r.hits.length === 0) return { title: `${where}에 조건에 맞는 곳이 없어요`, sub: range };
    if (r.conditions === 0) return { title: `${where} 인증 가게`, sub: `${range} · 여러 공공 목록에 실린 순` };
    const all = r.hits.filter((h) => h.matched.length === r.conditions).length;
    return {
      title: r.conditions > 1 ? `${where} · 조건을 모두 만족 ${all}곳` : `${where} · ${r.hits.length}곳`,
      sub: `${range} · 조건을 많이 만족한 순 → 실린 목록 수 → 거리`,
    };
  }

  const head = nearbyHead();
  return (
    <div className="app">
      <aside className="sidebar">
        <header className="sidebar-head">
          <h1>검증된 식당 지도</h1>
          <div className="search">
            <span className="icon" aria-hidden>⌕</span>
            <input
              type="text"
              value={query}
              placeholder="가게 이름, 장소, '대전역 근처 싼 노포'"
              aria-label="검색"
              onChange={(e) => onQueryChange(e.target.value)}
              onKeyDown={onKeyDown}
            />
            {(query || chipsOn || placeName) && (
              <button className="clear" aria-label="검색 지우기" onClick={clearAll}>×</button>
            )}
          </div>
          <FilterChips certs={certs} cats={cats} onCerts={setCerts} onCats={setCats} />
        </header>

        <div className="sidebar-body">
          {error && <p className="error" role="alert">{error}</p>}
          {parsed && !store && !building && <ParsedLine text={parsed.text} r={parsed.result} onClose={() => setParsed(null)} />}

          {store ? (
            <StorePanel store={store} onBack={() => setStore(null)} onBuilding={() => openBuilding(store.storeId)} />
          ) : building ? (
            <>
              <div className="list-head">
                <button className="back" onClick={() => setBuilding(null)}>← 닫기</button>
                <div><div className="title">같은 건물의 인증 가게 {building.length}곳</div></div>
              </div>
              <StoreList items={items} active={navigated ? active : -1} hitSources={hitSources} onPick={(it) => openStore(it.storeId)} onHover={setHover} />
            </>
          ) : nameMode ? (
            <>
              {places.length > 0 && (
                <ul className="place-list" aria-label="장소">
                  {places.map((p) => (
                    <li key={`${p.name}-${p.sgg}`} onClick={() => pickPlace(p)}>
                      <span className="pin" aria-hidden>📍</span>
                      <div>
                        <div className="name">{p.name}</div>
                        <div className="muted">{p.sgg} · 이 장소로 이동</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <div className="list-head">
                <div>
                  <div className="title">{nameLoading ? "찾는 중…" : items.length ? `가게 ${items.length}곳` : "이 근처에서 가게를 찾지 못했어요"}</div>
                  <div className="sub">가까운 순 · 엔터를 치면 문장으로 찾아요</div>
                </div>
              </div>
              <StoreList items={items} active={navigated ? active : -1} hitSources={null} onPick={(it) => openStore(it.storeId)} onHover={setHover} />
            </>
          ) : (
            <>
              <div className="list-head">
                <div>
                  <div className="title">{head.title}</div>
                  {head.sub && <div className="sub">{head.sub}</div>}
                </div>
              </div>
              <StoreList items={items} active={navigated ? active : -1} hitSources={hitSources} onPick={(it) => openStore(it.storeId)} onHover={setHover} />
            </>
          )}
        </div>
      </aside>

      <MapView onSelect={onMapSelect} onReady={onReady} selected={selected} results={mapResults} highlight={highlight} />
    </div>
  );
}

/** 자연어 해석 결과 한 줄: 무엇을 무엇으로 읽었는지, 무엇을 반영하지 못했는지 (결정 24·31번: 못 한 건 숨기지 않는다) */
function ParsedLine({ text, r, onClose }: { text: string; r: ParseResult; onClose: () => void }) {
  const label = (as: string) =>
    as === "place" ? `📍${r.place?.name}`
      : as === "popular" ? "실린 목록 많은 순"
      : CERT_CHIPS.find((c) => c.key === as)?.label ?? as;
  return (
    <div className="parsed">
      <button className="x" aria-label="닫기" onClick={onClose}>×</button>
      <div className="q">“{text}”</div>
      {r.used.length === 0 ? (
        <div>조건으로 읽을 말이 없어요. 가게 이름이면 목록에서 골라 주세요.</div>
      ) : (
        <div className="read">
          {r.used.map((u) => (
            <span key={u.word}><span className="muted">{u.word}</span> → {label(u.as)}</span>
          ))}
        </div>
      )}
      {r.unknown.length > 0 && <div className="unknown">반영 못 함: {r.unknown.join(", ")} · 공개 데이터에 없는 정보예요</div>}
    </div>
  );
}

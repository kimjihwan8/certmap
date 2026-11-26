/** 화면 전체: 지도 + (가게를 누르면) 상세 패널 */
import { useState } from "react";
import { fetchStore, type StoreDetail } from "./api";
import { MapView } from "./MapView";
import { StorePanel } from "./StorePanel";

export function App() {
  const [store, setStore] = useState<StoreDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function select(id: string) {
    setError(null);
    try {
      setStore(await fetchStore(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="app">
      <header className="title">
        <h1>검증된 식당 지도</h1>
        <div className="legend">
          <span><i className="dot blue" />공공 인증</span>
          <span><i className="dot orange" />LX 직원 추천</span>
          <span>큰 원 = 실린 목록이 많음</span>
        </div>
      </header>
      <MapView onSelect={select} />
      {error && <p className="error" role="alert">{error}</p>}
      {store && <StorePanel store={store} onClose={() => setStore(null)} />}
    </div>
  );
}

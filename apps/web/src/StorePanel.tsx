/**
 * 가게 상세 (사이드바 안). 점수나 평가 없이, 어떤 공공 목록에 실렸는지 사실만 보여준다 (결정 일지 1번).
 * 리뷰·사진은 우리 데이터에 없으므로 네이버·카카오 지도로 이어 주는 링크만 둔다 (크롤링은 하지 않는다).
 */
import { useState } from "react";
import type { StoreDetail } from "./api";
import { SOURCES } from "./labels";

// 좌표가 가게 자체가 아닐 때 알려준다 (결정 23번)
const COORD_NOTE: Record<string, string> = {
  building: "상가 정보에 없는 가게라, 같은 건물 위치로 표시했어요.",
  source: "상가 정보에 없는 가게라, 관광공사 좌표로 표시했어요.",
};

export function StorePanel({ store, onBack, onBuilding }: {
  store: StoreDetail;
  onBack: () => void;
  onBuilding: () => void;                 // "이 건물의 인증 가게" 목록 열기
}) {
  const [copied, setCopied] = useState(false);
  // 주소: 인증 원본 주소가 있으면 그걸, 없으면 건물 키('시도|도로명|본번-부번')를 읽기 좋게 바꾼다
  const addr = store.certs.find((c) => c.addr)?.addr ?? store.roadKey?.replaceAll("|", " ").replace(/-0$/, "") ?? "";
  // 이 가게 말고 같은 건물에 인증 가게가 더 있는지 (이 가게가 인증 가게면 자기 자신도 세어져 있다)
  const others = store.buildingCount - (store.certCount > 0 ? 1 : 0);
  // 외부 지도 검색어: 이름 + 주소 앞부분(시·구·도로명). 같은 이름 가게가 많아도 그 가게가 먼저 나오게
  const searchText = encodeURIComponent(`${store.name} ${addr.split(" ").slice(0, 3).join(" ")}`);

  async function copy() {
    try {
      await navigator.clipboard.writeText(addr);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 복사 권한이 없으면 아무 일도 하지 않는다 */
    }
  }

  return (
    <section className="detail" aria-label="가게 정보">
      <button className="back" onClick={onBack}>← 목록</button>
      <h2>
        {store.name}
        {store.branch && <span className="branch"> {store.branch}</span>}
      </h2>
      <p className="meta">{[store.category, store.floor && `${store.floor}층`].filter(Boolean).join(" · ")}</p>
      {addr && (
        <p className="addr">
          {addr}
          <button className="link" onClick={copy}>{copied ? "복사됨" : "복사"}</button>
        </p>
      )}
      <div className="actions">
        <a href={`https://map.naver.com/p/search/${searchText}`} target="_blank" rel="noreferrer">네이버 지도에서 보기</a>
        <a href={`https://map.kakao.com/?q=${searchText}`} target="_blank" rel="noreferrer">카카오맵에서 보기</a>
      </div>
      {COORD_NOTE[store.coordSource] && <p className="note">{COORD_NOTE[store.coordSource]}</p>}

      <h3>{store.certs.length ? `실린 공공 목록 ${store.certs.length}개` : "실린 공공 목록 없음"}</h3>
      {store.certs.length === 0 && <p className="none">공공 인증·추천 목록에 실리지 않은 가게예요.</p>}
      <ul className="certs">
        {store.certs.map((c, i) => {
          const src = SOURCES[c.source];
          return (
            <li key={i} style={{ "--c": src?.color ?? "#6b7280" } as React.CSSProperties}>
              <strong>{src?.label ?? c.source}</strong>
              {c.name !== store.name && <span className="as"> · {c.name}(으)로 등록</span>}
              {(c.certDate || c.validTo || c.sinceYear) && (
                <div className="sub">
                  {[c.certDate && `지정 ${c.certDate}`, c.validTo && `유효 ~${c.validTo}`, c.sinceYear && `인허가 ${c.sinceYear}년`]
                    .filter(Boolean).join(" · ")}
                </div>
              )}
              {c.menu && <div className="menu">{c.menu}</div>}
            </li>
          );
        })}
      </ul>

      {others > 0 && (
        <button className="building-link" onClick={onBuilding}>같은 건물의 다른 인증 가게 {others}곳 →</button>
      )}
    </section>
  );
}

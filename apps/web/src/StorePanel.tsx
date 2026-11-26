/**
 * 가게 상세 패널. 점수나 평가 없이, 어떤 공공 목록에 실렸는지 사실만 보여준다 (결정 일지 1번).
 */
import type { StoreDetail } from "./api";

// 인증 원본 이름 → 화면 표시. LX·관광공사는 인증이 아니므로 출처를 그대로 적는다 (결정 10·24번)
const SOURCE_LABEL: Record<string, string> = {
  모범음식점: "모범음식점",
  착한가격업소: "착한가격업소",
  백년가게: "백년가게",
  식품안심업소: "식품안심업소",
  안심식당: "안심식당",
  관광공사: "관광공사 관광정보에 실림",
  LX공사맛집: "LX 직원 추천",
};

// 좌표가 가게 자체가 아닐 때 알려준다 (결정 23번)
const COORD_NOTE: Record<string, string> = {
  building: "상가 정보에 없는 가게라, 같은 건물 위치로 표시했어요.",
  source: "상가 정보에 없는 가게라, 관광공사 좌표로 표시했어요.",
};

export function StorePanel({ store, onClose }: { store: StoreDetail; onClose: () => void }) {
  // 주소: 인증 원본 주소가 있으면 그걸, 없으면 건물 키('시도|도로명|본번-부번')를 읽기 좋게 바꾼다
  const addr = store.certs.find((c) => c.addr)?.addr ?? store.roadKey?.replaceAll("|", " ").replace(/-0$/, "");
  return (
    <aside className="panel" aria-label="가게 정보">
      <button className="close" onClick={onClose} aria-label="닫기">×</button>
      <h2>
        {store.name}
        {store.branch && <span className="branch"> {store.branch}</span>}
      </h2>
      <p className="meta">
        {[store.category, addr, store.floor && `${store.floor}층`].filter(Boolean).join(" · ")}
      </p>
      {COORD_NOTE[store.coordSource] && <p className="note">{COORD_NOTE[store.coordSource]}</p>}

      <h3>실린 공공 목록 {store.certs.length}개</h3>
      <ul className="certs">
        {store.certs.map((c, i) => (
          <li key={i}>
            <strong>{SOURCE_LABEL[c.source] ?? c.source}</strong>
            {c.name !== store.name && <span className="as"> ({c.name}(으)로 등록)</span>}
            <div className="detail">
              {[c.certDate && `지정 ${c.certDate}`, c.validTo && `유효 ~${c.validTo}`, c.sinceYear && `인허가 ${c.sinceYear}년`]
                .filter(Boolean).join(" · ")}
            </div>
            {c.menu && <div className="menu">{c.menu}</div>}
          </li>
        ))}
      </ul>
    </aside>
  );
}

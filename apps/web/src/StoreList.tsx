/**
 * 사이드바의 가게 목록 (네이버 지도식). 검색 결과·조건 결과·건물 목록이 같은 모양을 쓴다.
 * 점수나 별점 없이, 어떤 공공 목록에 실렸는지만 색 배지로 보여준다 (결정 일지 1번).
 * 칩을 골랐으면 그 칩을 만족하는 배지만 진하게, 나머지는 흐리게 칠한다.
 */
import { formatDistance, SOURCES } from "./labels";

export interface ListItem {
  storeId: string;
  name: string;
  branch: string | null;
  category: string | null;
  place?: string | null;       // 시군구 또는 층 ('중구', '3층')
  distance?: number;           // 건물 목록에는 없다
  sources: string[];           // 실린 인증 원본 이름들. 비어 있으면 '공공 인증 없음'
  categoryHit?: boolean;       // 업종 칩을 만족했는지 (업종 글자를 진하게)
  score?: { got: number; of: number };   // 조건 몇 개 중 몇 개를 만족했는지
}

export function StoreList({ items, active, hitSources, onPick, onHover }: {
  items: ListItem[];
  active: number;                         // 키보드·마우스로 가리킨 줄
  hitSources: string[] | null;            // 고른 칩이 가리키는 인증 원본. null = 칩 없음 (모든 배지를 보통으로)
  onPick: (item: ListItem) => void;
  onHover: (index: number | null) => void;
}) {
  return (
    <ul className="store-list" role="listbox" aria-label="가게 목록" onMouseLeave={() => onHover(null)}>
      {items.map((it, i) => (
        <li
          key={it.storeId}
          role="option"
          aria-selected={i === active}
          className={i === active ? "active" : ""}
          onClick={() => onPick(it)}
          onMouseEnter={() => onHover(i)}
        >
          <div className="title-row">
            <span className="name">{it.name}</span>
            {it.branch && <span className="branch">{it.branch}</span>}
            {it.score && it.score.of > 1 && (
              <span className={it.score.got === it.score.of ? "score full" : "score"}>
                {it.score.got}/{it.score.of}
              </span>
            )}
          </div>
          <div className="info-row">
            {[it.distance !== undefined && formatDistance(it.distance), it.place].filter(Boolean).join(" · ")}
            {it.category && <span className={it.categoryHit ? "category hit" : "category"}>{it.category}</span>}
          </div>
          <div className="badges">
            {it.sources.length === 0 && <span className="badge none">공공 인증 없음</span>}
            {it.sources.map((s) => {
              const src = SOURCES[s];
              const dim = hitSources !== null && !hitSources.includes(s);
              return (
                <span key={s} className={dim ? "badge dim" : "badge"} style={{ "--c": src?.color ?? "#6b7280" } as React.CSSProperties}>
                  {src?.short ?? s}
                </span>
              );
            })}
          </div>
        </li>
      ))}
    </ul>
  );
}

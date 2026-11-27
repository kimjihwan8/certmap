/**
 * "소개글로 찾은 곳": 칩으로 못 읽은 말("분위기 좋은")을 관광공사 소개글에서 찾은 결과. 결정 일지 37번.
 * 정밀도가 62% 라 틀린 결과도 섞인다. 그래서 가게마다 걸린 문장을 그대로 보여주고, 맞는지는 사용자가 판단하게 한다.
 * 점수나 '추천'이라는 말은 쓰지 않는다 — 소개글에 이렇게 적혀 있다는 사실만 보여준다 (결정 1번).
 */
import { useEffect, useRef, useState } from "react";
import { type CertFilter, searchVibe, type VibeResult } from "./api";
import { formatDistance } from "./labels";

/** 칩 조건(certs·cats)을 같이 넘긴다: "분위기 좋은 국밥집"이면 국밥집 중에서 분위기를 찾는다 */
export function useVibe(q: string, center: { lat: number; lon: number }, certs: CertFilter[], cats: string[]) {
  const [result, setResult] = useState<VibeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);
  const key = JSON.stringify([q, center, certs, cats]);
  useEffect(() => {
    if (!q) {
      latest.current++;
      setResult(null);
      return;
    }
    setLoading(true);
    const id = ++latest.current;
    searchVibe({ q, ...center, certs, cats })
      .then((r) => id === latest.current && setResult(r))
      .catch(() => id === latest.current && setResult(null))
      .finally(() => id === latest.current && setLoading(false));
  }, [key]);
  return { result, loading };
}

export function VibeSection({ q, result, loading, onPick, onHover }: {
  q: string;
  result: VibeResult | null;
  loading: boolean;
  onPick: (storeId: string) => void;
  onHover: (point: { lat: number; lon: number } | null) => void;
}) {
  const where = result && (result.radius ? `${formatDistance(result.radius)} 안` : "전국");
  return (
    <section className="vibe" aria-label="소개글로 찾은 곳">
      <div className="vibe-head">
        <div className="title">소개글로 찾은 곳 · “{q}”</div>
        <div className="sub">
          {loading ? "소개글을 읽는 중…" : `${where ?? ""} · 관광공사 소개글이 있는 가게에서만 찾아요. 맞는지는 문장을 보고 판단해 주세요`}
        </div>
      </div>
      {!loading && result?.hits.length === 0 && <p className="muted vibe-empty">소개글에서 찾지 못했어요</p>}
      <ul onMouseLeave={() => onHover(null)}>
        {result?.hits.map((h) => (
          <li key={h.storeId} onClick={() => onPick(h.storeId)} onMouseEnter={() => onHover({ lat: h.lat, lon: h.lon })}>
            <div className="title-row">
              <span className="name">{h.name}</span>
              {h.branch && <span className="branch">{h.branch}</span>}
            </div>
            <div className="info-row">{[formatDistance(h.distance), h.sgg, h.category].filter(Boolean).join(" · ")}</div>
            <blockquote>{h.evidence}</blockquote>
          </li>
        ))}
      </ul>
    </section>
  );
}

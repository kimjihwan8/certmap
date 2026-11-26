/**
 * 조건 칩: 인증 종류 6개 + 업종(상가 소분류). 결정 일지 30번.
 * 한 줄 가로 스크롤 — 두 줄로 쌓이면 목록이 아래로 밀린다.
 * 자연어 검색이 "대전역 근처 싼 노포"를 이 칩들로 바꿔 채운다. 그래서 칩이 곧 "반영한 조건" 표시가 된다.
 */
import { useEffect, useState } from "react";
import { type CertFilter, fetchCategories } from "./api";
import { CERT_CHIPS } from "./labels";

export function FilterChips({ certs, cats, onCerts, onCats }: {
  certs: CertFilter[];
  cats: string[];
  onCerts: (v: CertFilter[]) => void;
  onCats: (v: string[]) => void;
}) {
  const [open, setOpen] = useState(false);              // 업종 목록 펼침
  const [categories, setCategories] = useState<{ name: string; count: number }[]>([]);

  useEffect(() => {
    if (open && categories.length === 0) fetchCategories().then(setCategories).catch(() => {});
  }, [open, categories.length]);

  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const any = certs.length > 0 || cats.length > 0;

  return (
    <div className="filters">
      <div className="chips" role="group" aria-label="조건">
        <button
          className={cats.length ? "chip on" : "chip"}
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          {cats.length === 1 ? cats[0] : cats.length > 1 ? `업종 ${cats.length}` : "업종"} ▾
        </button>
        {CERT_CHIPS.map((c) => (
          <button
            key={c.key}
            className={certs.includes(c.key) ? "chip on" : "chip"}
            aria-pressed={certs.includes(c.key)}
            onClick={() => onCerts(toggle(certs, c.key))}
          >
            {c.label}
          </button>
        ))}
        {any && (
          <button className="chip clear" onClick={() => { onCerts([]); onCats([]); setOpen(false); }}>초기화</button>
        )}
      </div>
      {open && (
        <div className="category-panel">
          {categories.length === 0 && <p className="muted">불러오는 중…</p>}
          <div className="category-grid">
            {categories.map((c) => (
              <label key={c.name} className={cats.includes(c.name) ? "on" : ""}>
                <input type="checkbox" checked={cats.includes(c.name)} onChange={() => onCats(toggle(cats, c.name))} />
                <span>{c.name}</span> <span className="muted">{c.count.toLocaleString()}</span>
              </label>
            ))}
          </div>
          <button className="done" onClick={() => setOpen(false)}>닫기</button>
        </div>
      )}
    </div>
  );
}

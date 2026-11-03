"use client";
// پنل کوچک «جزئیات کم» کارت‌های خلاصه مدیریتی: عدد اصلی، چند واقعیت کوتاه، یک فهرست کوتاه و دکمه رفتن به صفحه کامل.
import { createContext, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import "./peek-panel.css";

export type Peek = {
  title: string;
  value: string;
  unit?: string;
  tone?: "neutral" | "good" | "watch" | "follow";
  facts?: { label: string; value: string }[];
  list?: { title: string; rows: { label: string; value: string; sub?: string; share?: number }[] };
  note?: string;
  page: string;
  onGo?: () => void;
};

export const PeekContext = createContext<(peek: Peek) => void>(() => undefined);
export const usePeek = () => useContext(PeekContext);

export function PeekPanel({ peek, onClose }: { peek: Peek | null; onClose: () => void }) {
  const [mounted, setMounted] = useState(false);
  const [shown, setShown] = useState<Peek | null>(null);
  useEffect(() => setMounted(true), []);
  // محتوای آخر را تا پایان انیمیشن بستن نگه می‌داریم تا پنل خالی نلغزد.
  useEffect(() => { if (peek) setShown(peek); }, [peek]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!mounted) return null;
  const p = peek || shown;
  const open = Boolean(peek);
  return createPortal(<>
    <div className={`pk-overlay ${open ? "open" : ""}`} onClick={onClose} />
    <div className={`pk-panel ${open ? "open" : ""} ${p?.tone || "neutral"}`} role="dialog" aria-modal="true" aria-hidden={!open}>
      {p && <>
        <div className="pk-head">
          <h3>{p.title}</h3>
          <button className="pk-close" onClick={onClose} aria-label="بستن">✕</button>
        </div>
        <div className="pk-value"><b>{p.value}</b>{p.unit && <span>{p.unit}</span>}</div>
        {p.facts && p.facts.length > 0 && <div className="pk-facts">
          {p.facts.map((f) => <div key={f.label}><small>{f.label}</small><b>{f.value}</b></div>)}
        </div>}
        {p.list && p.list.rows.length > 0 && <div className="pk-list">
          <h4>{p.list.title}</h4>
          {p.list.rows.map((r, i) => <div key={`${r.label}-${i}`} className="pk-row">
            <span className="pk-row-label">{r.label}{r.sub && <small>{r.sub}</small>}</span>
            {typeof r.share === "number" && <span className="pk-track"><i style={{ width: `${Math.max(2, Math.min(100, r.share))}%` }} /></span>}
            <b>{r.value}</b>
          </div>)}
        </div>}
        {p.note && <p className="pk-note">{p.note}</p>}
        {p.onGo && <button className="pk-go" onClick={() => { onClose(); p.onGo?.(); }}>مشاهده کامل در صفحه «{p.page}» ←</button>}
      </>}
    </div>
  </>, document.body);
}

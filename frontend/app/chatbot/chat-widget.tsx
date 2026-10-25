"use client";
// چت‌بات اپ — همه رابط کاربری‌اش در همین پوشه (frontend/app/chatbot) است؛ Backend: backend/app/chatbot.
// دکمه گرد پایین صفحه پنجره چت را باز می‌کند. پایین پنجره پیشنهادهای آماده (مخصوص صفحه فعلی) هست و
// هر جواب می‌تواند دکمه «برو به …» داشته باشد که همان صفحه اپ را باز می‌کند.
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import ChequeStatusDrawer, { type ChequeStatusInitial, type ChequeStatusKind } from "../management/cheque-status-drawer";
import { sendChatLink } from "./chat-link";
import "./chatbot.css";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const API = () => `http://${apiHost()}:8000/api/v1/chatbot`;

type Show = { panel: ChequeStatusKind } & ChequeStatusInitial;
type Link = { view: string; source?: "rahkaran" | "karamad"; search?: string; ref?: string; tab?: string; year?: number; month?: number; label?: string };
type Msg = { role: "user" | "assistant"; text: string; go?: string[]; choices?: string[]; show?: Show | null; link?: Link | null; error?: boolean };
const SHOW_TITLE: Record<ChequeStatusKind, string> = { returned: "چک‌های برگشتی", undetermined: "چک‌های تعیین تکلیف نشده" };

/** **پررنگ** و خطوط «•» را بدون کتابخانه markdown نمایش می‌دهد. */
function RichText({ text }: { text: string }) {
  return <>{text.split("\n").map((line, i) => {
    const parts: ReactNode[] = line.split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
      p.startsWith("**") && p.endsWith("**") ? <b key={j}>{p.slice(2, -2)}</b> : p);
    return <p key={i} className={/^\s*[•\-]/.test(line) ? "cb-bullet" : undefined}>{parts}</p>;
  })}</>;
}

export default function ChatWidget({ view, go }: { view: string; go: (view: string) => void }) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [pages, setPages] = useState<Record<string, string>>({});
  // فهرستی که چت‌بات کنار گفتگو باز کرده (پنل برگشتی / تعیین تکلیف نشده)
  const [shown, setShown] = useState<Show | null>(null);
  // بعد از باز کردن لینک فیلترشده، چت به سمت راست می‌رود تا جدول صفحه زیرش پنهان نشود.
  const [linkDock, setLinkDock] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => setMounted(true), []);
  // پیشنهادهای آماده مخصوص صفحه فعلی
  useEffect(() => {
    fetch(`${API()}/suggestions?view=${encodeURIComponent(view)}`).then((r) => r.json())
      .then((j) => { setSuggestions(j.suggestions || []); setPages(j.pages || {}); }).catch(() => undefined);
  }, [view]);
  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" }); }, [messages, busy]);
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 250); }, [open]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || busy) return;
    const history = messages.filter((m) => !m.error).slice(-10).map((m) => ({ role: m.role, text: m.text }));
    setMessages((m) => [...m, { role: "user", text: message }]);
    setInput("");
    setBusy(true);
    try {
      const r = await fetch(`${API()}/ask`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history, view }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw Error(typeof j.detail === "string" ? j.detail : `خطای ${r.status}`);
      setMessages((m) => [...m, { role: "assistant", text: j.answer, go: j.go, choices: j.choices, show: j.show, link: j.link }]);
      if (j.show?.panel) setShown({ ...j.show });
      if (j.link?.view) openLink(j.link);
      if (j.followups?.length) setSuggestions(j.followups);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `پاسخ دریافت نشد: ${e instanceof Error ? e.message : "خطا"}`, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  // لینک فیلترشده: صفحه مقصد را باز کن و منبع/جستجو را بفرست (صفحه با useChatLink اعمالش می‌کند).
  function openLink(link: Link) {
    setShown(null);
    setLinkDock(true);
    go(link.view);
    // یک لحظه بعد از عوض شدن صفحه بفرست تا صفحه مقصد آماده دریافت باشد
    window.setTimeout(() => sendChatLink({ view: link.view, source: link.source, search: link.search, ref: link.ref, tab: link.tab, year: link.year, month: link.month }), 60);
  }

  if (!mounted) return null;
  return createPortal(<>
    <ChequeStatusDrawer kind={shown?.panel || null} initial={shown || undefined} onClose={() => setShown(null)}
      onOpenPage={() => { setShown(null); setOpen(false); go("receivedCheques"); }} />
    <button type="button" className={`cb-fab${open ? " open" : ""}${shown || linkDock ? " docked" : ""}`} onClick={() => { if (open) setLinkDock(false); setOpen(!open); }} aria-label={open ? "بستن دستیار" : "باز کردن دستیار هوشمند اکسیر"}>
      {open ? "✕" : <><span className="cb-fab-icon">💬</span><span className="cb-fab-label">دستیار هوشمند اکسیر</span></>}
    </button>
    <div className={`cb-panel${open ? " open" : ""}${shown || linkDock ? " docked" : ""}`} role="dialog" aria-label="دستیار هوشمند اکسیر" aria-hidden={!open}>
      <div className="cb-head">
        <div><b>دستیار هوشمند اکسیر</b><small>فقط درباره داده‌ها و صفحه‌های همین اپ</small></div>
        {messages.length > 0 && <button type="button" className="cb-clear" onClick={() => setMessages([])} title="گفتگوی جدید">↺</button>}
      </div>
      <div className="cb-list" ref={listRef}>
        {!messages.length && <div className="cb-empty">
          <span>👋</span>
          <p>سلام! درباره چک‌ها، مشتریان، پرداخت تجاری، نقدینگی، توزیع بار، اسناد خرید و انبار بپرسید؛ یا بپرسید هر صفحه چیه و برای کاری کجا بروید.</p>
        </div>}
        {messages.map((m, i) => <div key={i} className={`cb-msg ${m.role}${m.error ? " error" : ""}`}>
          <div className="cb-bubble"><RichText text={m.text} /></div>
          {/* «کدام یکی؟» — چند مشتری/کالا/طرف حساب پیدا شده؛ کلیک = ارسال همان گزینه */}
          {m.choices && m.choices.length > 0 && <div className="cb-choices">
            {m.choices.map((c) => <button type="button" key={c} disabled={busy} onClick={() => send(c)}>{c}</button>)}
          </div>}
          {((m.go && m.go.length > 0) || m.show || m.link) && <div className="cb-go">
            {m.link && <button type="button" className="cb-link" onClick={() => openLink(m.link!)}>🔗 {m.link.label || `باز کردن «${pages[m.link.view] || m.link.view}»${m.link.search ? ` · ${m.link.search}` : ""}`}</button>}
            {m.show && <button type="button" className="cb-show" onClick={() => setShown({ ...m.show! })}>☰ نمایش فهرست {SHOW_TITLE[m.show.panel]}</button>}
            {(m.go || []).map((v) => <button type="button" key={v} onClick={() => { go(v); setOpen(false); setShown(null); }}>برو به «{pages[v] || v}» ←</button>)}
          </div>}
        </div>)}
        {busy && <div className="cb-msg assistant"><div className="cb-bubble cb-typing"><i /><i /><i /></div></div>}
      </div>
      {suggestions.length > 0 && <div className="cb-suggest">
        {suggestions.map((s) => <button type="button" key={s} disabled={busy} onClick={() => send(s)}>{s}</button>)}
      </div>}
      <form className="cb-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <textarea ref={inputRef} value={input} rows={1} maxLength={2000} placeholder="سؤالتان را بنویسید…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} />
        <button type="submit" disabled={busy || !input.trim()} aria-label="ارسال">➤</button>
      </form>
    </div>
  </>, document.body);
}

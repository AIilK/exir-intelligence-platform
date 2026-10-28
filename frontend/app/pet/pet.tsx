"use client";
// حیوان خانگی اپ: هر کاربر گربه، سگ یا … انتخاب می‌کند (preferences.pet روی سرور). پایین صفحه راه می‌رود،
// می‌نشیند، وقتی کاربر کاری نمی‌کند می‌خوابد، یادآوری‌های شخصی (/api/v1/reminders) را سر وقت می‌گوید
// و الارم‌های باز همان شخص را یادش می‌اندازد. با کلیک روی حیوان منوی آن باز می‌شود.
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "../auth/auth";
import { useAlarms } from "../alarms/alarms";
import "./pet.css";

export const PETS: { key: string; emoji: string; label: string; walker: boolean }[] = [
  { key: "cat", emoji: "🐈", label: "گربه", walker: true },
  { key: "blackcat", emoji: "🐈‍⬛", label: "گربه سیاه", walker: true },
  { key: "kitty", emoji: "🐱", label: "بچه‌گربه", walker: false },
  { key: "dog", emoji: "🐕", label: "سگ", walker: true },
  { key: "poodle", emoji: "🐩", label: "پودل", walker: true },
  { key: "guide", emoji: "🦮", label: "سگ راهنما", walker: true },
  { key: "puppy", emoji: "🐶", label: "توله‌سگ", walker: false },
  { key: "rabbit", emoji: "🐇", label: "خرگوش", walker: true },
  { key: "fox", emoji: "🦊", label: "روباه", walker: false },
  { key: "panda", emoji: "🐼", label: "پاندا", walker: false },
];
export const petOf = (key?: string) => PETS.find((p) => p.key === key);
const isDog = (key: string) => ["dog", "poodle", "guide", "puppy"].includes(key);

type Reminder = { id: number; text: string; due_at: string | null; done: boolean };
type Mode = "walk" | "sit" | "sleep";
type Bubble = { text: string; kind?: "reminder" | "alarm" | "info"; reminder?: Reminder } | null;

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const API = () => `http://${apiHost()}:8000/api/v1/reminders`;
const IDLE_SLEEP_MS = 90_000;      // بی‌کاری کاربر تا خوابیدن
const POLL_MS = 30_000;            // بررسی یادآوری‌های سررسیده
const ALARM_NAG_MS = 15 * 60_000;  // هر ربع ساعت یک بار الارم باز را یادآوری می‌کند
const SPEED = 55;                  // پیکسل در ثانیه
const faNum = (n: number) => n.toLocaleString("fa-IR");
const whenFa = (iso: string | null) => {
  if (!iso) return "بدون زمان";
  try { return new Intl.DateTimeFormat("fa-IR-u-ca-persian", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)); }
  catch { return iso.slice(0, 16); }
};
async function api(path = "", options?: RequestInit) {
  const r = await fetch(`${API()}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(options?.headers || {}) } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(typeof j.detail === "string" ? j.detail : `خطای ${r.status}`);
  return j;
}
const reduceMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function track() {
  // پایین صفحه، دور از دکمه چت (چپ) و منوی کناری (راست)
  const w = typeof window !== "undefined" ? window.innerWidth : 1200;
  const min = Math.min(300, w * 0.3), max = Math.max(min + 40, w - (w > 860 ? 300 : 80));
  return { min, max };
}

/** حیوان خانگی + منو. onGo: رفتن به صفحه (view مالی یا مسیر داشبورد یکپارچه). */
export default function Pet({ onGo }: { onGo?: (view: string) => void }) {
  const { profile, setPreferences } = useAuth();
  const { alarms, loaded } = useAlarms();
  const pet = petOf(profile.user.preferences?.pet ?? "cat");
  const petName = profile.user.preferences?.pet_name || (pet ? pet.label : "");
  const firstName = profile.user.full_name.split(" ")[0];

  const [mounted, setMounted] = useState(false);
  const [x, setX] = useState(() => track().min + 80);
  const [dur, setDur] = useState(0);
  const [faceRight, setFaceRight] = useState(false);
  const [mode, setMode] = useState<Mode>("sit");
  const [sleepLock, setSleepLock] = useState(false);
  const [bubble, setBubble] = useState<Bubble>(null);
  const [menu, setMenu] = useState(false);
  const [picker, setPicker] = useState(false);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const lastActivity = useRef(Date.now());
  const told = useRef<Set<number>>(new Set());
  const greeted = useRef(false);
  const lastNag = useRef(Date.now());
  const xRef = useRef(x);
  xRef.current = x;

  useEffect(() => setMounted(true), []);

  // ---------------------------------------------------------------- راه رفتن، نشستن، خوابیدن
  useEffect(() => {
    if (!pet) return;
    let timer = 0;
    const step = () => {
      const idle = Date.now() - lastActivity.current;
      if (sleepLock || idle > IDLE_SLEEP_MS) {
        setMode("sleep");
      } else if (bubble || menu || reduceMotion()) {
        setMode("sit");
      } else if (Math.random() < 0.35) {
        setMode("sit");
      } else {
        const { min, max } = track();
        const target = Math.round(min + Math.random() * (max - min));
        const seconds = Math.max(1.2, Math.abs(target - xRef.current) / SPEED);
        setFaceRight(target > xRef.current);
        setDur(seconds);
        setMode("walk");
        setX(target);
        timer = window.setTimeout(() => { setMode("sit"); timer = window.setTimeout(step, 2500 + Math.random() * 4000); }, seconds * 1000);
        return;
      }
      timer = window.setTimeout(step, 3500 + Math.random() * 4500);
    };
    timer = window.setTimeout(step, 1500);
    return () => window.clearTimeout(timer);
  }, [pet, bubble, menu, sleepLock]);

  // هر فعالیت کاربر حیوان را بیدار می‌کند (مگر خودش گفته باشد «بخواب»)
  useEffect(() => {
    const wake = () => {
      const wasIdle = Date.now() - lastActivity.current > IDLE_SLEEP_MS;
      lastActivity.current = Date.now();
      if (wasIdle && !sleepLock) setMode("sit");
    };
    window.addEventListener("mousemove", wake, { passive: true });
    window.addEventListener("keydown", wake);
    return () => { window.removeEventListener("mousemove", wake); window.removeEventListener("keydown", wake); };
  }, [sleepLock]);

  // ---------------------------------------------------------------- یادآوری‌ها
  const loadReminders = useCallback(() => api().then((j) => setReminders(j.reminders || [])).catch(() => undefined), []);
  useEffect(() => {
    if (!pet) return;
    void loadReminders();
    const t = window.setInterval(() => void loadReminders(), POLL_MS);
    return () => window.clearInterval(t);
  }, [pet, loadReminders]);
  const say = useCallback((b: Bubble) => {
    setBubble(b);
    setSleepLock(false);
    lastActivity.current = Date.now();
    setMode("sit");
  }, []);
  // یادآوری سررسیده → می‌آید وسط و می‌گوید
  useEffect(() => {
    if (!pet || bubble) return;
    const due = reminders.find((r) => !r.done && r.due_at && new Date(r.due_at).getTime() <= Date.now() && !told.current.has(r.id));
    if (due) {
      told.current.add(due.id);
      const { min, max } = track();
      const target = Math.round((min + max) / 2);
      setFaceRight(target > xRef.current);
      setDur(Math.max(0.8, Math.abs(target - xRef.current) / (SPEED * 2.5)));
      setX(target);
      say({ text: `${firstName}، یادت نره: ${due.text}`, kind: "reminder", reminder: due });
    }
  }, [pet, reminders, bubble, firstName, say]);
  // سلام اول و یادآوری الارم‌های باز
  useEffect(() => {
    if (!pet || !loaded || bubble) return;
    const open = alarms.filter((a) => a.my_status === "open" || a.my_status === "seen");
    const hot = open.filter((a) => a.level === "critical" || a.level === "high");
    if (!greeted.current) {
      greeted.current = true;
      const sound = isDog(pet.key) ? "هاپ هاپ!" : pet.key.includes("cat") || pet.key === "kitty" ? "میو!" : "سلام!";
      say({ text: open.length ? `${sound} سلام ${firstName}! ${faNum(open.length)} الارم باز داری${hot.length ? `؛ ${faNum(hot.length)} تاش مهمه` : ""}.` : `${sound} سلام ${firstName}! امروز الارم بازی نداری 🌿`, kind: open.length ? "alarm" : "info" });
      return;
    }
    if (hot.length && Date.now() - lastNag.current > ALARM_NAG_MS && Date.now() - lastActivity.current < IDLE_SLEEP_MS) {
      lastNag.current = Date.now();
      say({ text: `هنوز این باز مونده: ${hot[0].title}`, kind: "alarm" });
    }
  }, [pet, loaded, alarms, bubble, firstName, say]);
  // حباب خودبه‌خود بسته می‌شود (جز یادآوری که جواب می‌خواهد)
  useEffect(() => {
    if (!bubble || bubble.kind === "reminder") return;
    const t = window.setTimeout(() => setBubble(null), 9000);
    return () => window.clearTimeout(t);
  }, [bubble]);

  const done = async (r: Reminder) => {
    setBubble(null);
    await api(`/${r.id}`, { method: "PATCH", body: JSON.stringify({ done: true }) }).catch(() => undefined);
    void loadReminders();
  };
  const snooze = async (r: Reminder, minutes: number) => {
    setBubble(null);
    told.current.delete(r.id);
    await api(`/${r.id}`, { method: "PATCH", body: JSON.stringify({ due_at: new Date(Date.now() + minutes * 60_000).toISOString() }) }).catch(() => undefined);
    void loadReminders();
  };

  if (!mounted || !pet) return null;
  const sleeping = mode === "sleep";
  return createPortal(<div className="pet-layer" aria-live="polite">
    <div className={`pet ${mode}${pet.walker ? " walker" : ""}`} style={{ left: x, transitionDuration: `${dur}s` }}>
      {bubble && !menu && <div className={`pet-bubble ${bubble.kind || "info"}`}>
        <button type="button" className="pet-x" onClick={() => setBubble(null)} aria-label="بستن">✕</button>
        <p>{bubble.text}</p>
        {bubble.reminder && <div className="pet-actions">
          <button type="button" onClick={() => done(bubble.reminder!)}>✓ انجام شد</button>
          <button type="button" onClick={() => snooze(bubble.reminder!, 10)}>⏰ ۱۰ دقیقه بعد</button>
          <button type="button" onClick={() => snooze(bubble.reminder!, 60)}>یک ساعت بعد</button>
        </div>}
        {bubble.kind === "alarm" && onGo && <div className="pet-actions">
          <button type="button" onClick={() => { setBubble(null); onGo("alerts"); }}>ببینم ←</button>
        </div>}
      </div>}
      {sleeping && <span className="pet-zzz" aria-hidden><i>z</i><i>z</i><i>z</i></span>}
      <button type="button" className="pet-body" onClick={() => { setMenu(!menu); setPicker(false); setBubble(null); lastActivity.current = Date.now(); }}
        title={`${petName} — برای یادآوری‌ها و تنظیمات کلیک کنید`} aria-label={`${petName}: منوی حیوان خانگی`}>
        <span className="pet-emoji" style={{ transform: pet.walker && faceRight ? "scaleX(-1)" : undefined }}>{pet.emoji}</span>
        <span className="pet-shadow" aria-hidden />
      </button>
      {menu && <PetMenu petName={petName} sleeping={sleeping} reminders={reminders} picker={picker} setPicker={setPicker}
        onClose={() => setMenu(false)} reload={loadReminders} onDone={done}
        onSleep={() => { setSleepLock(true); setMode("sleep"); setMenu(false); }}
        onWake={() => { setSleepLock(false); lastActivity.current = Date.now(); setMode("sit"); setMenu(false); say({ text: "بیدار شدم! ☀" }); }}
        onPick={(key) => { setPreferences({ pet: key }); setPicker(false); if (key === "none") setMenu(false); }}
        onRename={(name) => setPreferences({ pet_name: name })} />}
    </div>
  </div>, document.body);
}

const DUE_OPTIONS: [string, string][] = [["none", "بدون زمان"], ["15", "۱۵ دقیقه بعد"], ["60", "یک ساعت بعد"], ["tomorrow", "فردا ساعت ۹"], ["custom", "زمان دلخواه…"]];

function PetMenu({ petName, sleeping, reminders, picker, setPicker, onClose, reload, onDone, onSleep, onWake, onPick, onRename }: {
  petName: string; sleeping: boolean; reminders: Reminder[]; picker: boolean; setPicker: (v: boolean) => void; onClose: () => void;
  reload: () => void; onDone: (r: Reminder) => void; onSleep: () => void; onWake: () => void; onPick: (key: string) => void; onRename: (name: string) => void;
}) {
  const [text, setText] = useState("");
  const [due, setDue] = useState("60");
  const [custom, setCustom] = useState("");
  const [name, setName] = useState(petName);
  const [error, setError] = useState("");
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    let dueAt: Date | null = null;
    if (due === "15" || due === "60") dueAt = new Date(Date.now() + Number(due) * 60_000);
    if (due === "tomorrow") { dueAt = new Date(); dueAt.setDate(dueAt.getDate() + 1); dueAt.setHours(9, 0, 0, 0); }
    if (due === "custom") { if (!custom) { setError("زمان را انتخاب کنید."); return; } dueAt = new Date(custom); }
    try {
      await api("", { method: "POST", body: JSON.stringify({ text, due_at: dueAt ? dueAt.toISOString() : null }) });
      setText(""); reload();
    } catch (err) { setError(err instanceof Error ? err.message : "ذخیره نشد"); }
  };
  const remove = async (r: Reminder) => { await api(`/${r.id}`, { method: "DELETE" }).catch(() => undefined); reload(); };
  return <div className="pet-menu" role="dialog" aria-label="منوی حیوان خانگی">
    <header>
      <input value={name} maxLength={30} onChange={(e) => setName(e.target.value)} onBlur={() => name.trim() && name !== petName && onRename(name.trim())}
        aria-label="اسم حیوان" title="اسمش را عوض کنید" />
      <button type="button" className="pet-x" onClick={onClose} aria-label="بستن">✕</button>
    </header>
    {picker ? <div className="pet-picker">
      {PETS.map((p) => <button key={p.key} type="button" onClick={() => onPick(p.key)} title={p.label}><span>{p.emoji}</span>{p.label}</button>)}
      <button type="button" className="hide" onClick={() => onPick("none")}><span>🙈</span>مخفی کن</button>
    </div> : <>
      <h4>یادآوری‌های من ({faNum(reminders.length)})</h4>
      <ul className="pet-list">
        {reminders.map((r) => <li key={r.id} className={r.due_at && new Date(r.due_at).getTime() <= Date.now() ? "due" : ""}>
          <button type="button" className="pet-check" onClick={() => onDone(r)} title="انجام شد">✓</button>
          <span>{r.text}<small>{whenFa(r.due_at)}</small></span>
          <button type="button" className="pet-del" onClick={() => remove(r)} aria-label="حذف">🗑</button>
        </li>)}
        {!reminders.length && <li className="empty">کاری برای یادآوری نداری 🌿</li>}
      </ul>
      <form className="pet-add" onSubmit={add}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="مثلاً: پیگیری چک‌های شمس" maxLength={300} required />
        <select value={due} onChange={(e) => setDue(e.target.value)} aria-label="زمان یادآوری">
          {DUE_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        {due === "custom" && <input type="datetime-local" value={custom} onChange={(e) => setCustom(e.target.value)} />}
        <button type="submit">+ یادم بنداز</button>
      </form>
      {error && <p className="pet-error">{error}</p>}
      <div className="pet-row">
        {sleeping ? <button type="button" onClick={onWake}>☀ بیدار شو</button> : <button type="button" onClick={onSleep}>😴 بخواب</button>}
        <button type="button" onClick={() => setPicker(true)}>🐾 عوض کردن حیوان</button>
      </div>
    </>}
  </div>;
}

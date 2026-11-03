"use client";
// دکمه «تم» بالای صفحه: رنگ تأکید و والپیپر؛ انتخاب هر کاربر روی سرور ذخیره می‌شود.
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/auth";
import { THEMES, WALLPAPERS, applyLook } from "./theme";
import { PETS } from "../pet/pet";
import "./theme.css";

export default function ThemePicker() {
  const { profile, setPreferences } = useAuth();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const look = profile.user.preferences || {};
  const theme = look.theme || "teal", wallpaper = look.wallpaper || "none";
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  // همیشه ظاهر کامل (تم + والپیپر) از وضعیت فعلی صفحه ساخته و ذخیره می‌شود تا دو انتخاب پشت‌سرهم همدیگر را پاک نکنند.
  const pick = (next: { theme?: string; wallpaper?: string }) => {
    const root = document.documentElement.dataset;
    const look = { theme: root.theme || theme, wallpaper: root.wallpaper || wallpaper, ...next };
    applyLook(look);
    setPreferences(look);
  };
  return <div className="look" ref={box} style={{ position: "relative" }}>
    <button type="button" className="look-btn" onClick={() => setOpen(!open)} aria-expanded={open}><i />تم</button>
    {open && <div className="look-pop" role="dialog" aria-label="انتخاب تم و والپیپر">
      <h4>رنگ تأکید</h4>
      <div className="look-swatches">
        {THEMES.map((t) => <button key={t.key} type="button" title={t.label} aria-label={t.label} className={theme === t.key ? "on" : ""}
          style={{ background: t.key === "rainbow" ? "conic-gradient(#f472b6,#fbbf24,#4ade80,#38bdf8,#a78bfa,#f472b6)" : `linear-gradient(135deg,${t.colors[0]},${t.colors[1]})` }}
          onClick={() => pick({ theme: t.key })} />)}
      </div>
      <h4>والپیپر</h4>
      <div className="look-walls">
        {WALLPAPERS.map((w) => <button key={w.key} type="button" className={wallpaper === w.key ? "on" : ""} onClick={() => pick({ wallpaper: w.key })}>
          <span style={{ background: w.preview }} />{w.label}
        </button>)}
      </div>
      <h4>حیوان خانگی (پایین صفحه راه می‌رود و کارهایت را یادت می‌اندازد)</h4>
      <div className="look-pets">
        {PETS.map((p) => <button key={p.key} type="button" title={p.label} aria-label={p.label} className={(look.pet ?? "cat") === p.key ? "on" : ""}
          onClick={() => setPreferences({ pet: p.key })}>{p.emoji}</button>)}
        <button type="button" title="بدون حیوان" aria-label="بدون حیوان" className={look.pet === "none" ? "on" : ""} onClick={() => setPreferences({ pet: "none" })}>🚫</button>
      </div>
    </div>}
  </div>;
}

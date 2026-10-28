"use client";
// صفحه ورود. اگر هنوز هیچ کاربری نیست (نصب تازه)، همین صفحه «ساخت مدیر سیستم» را نشان می‌دهد.
import { useState } from "react";
import type { FormEvent } from "react";
import { authJson, type Profile } from "./auth";
import "./auth.css";

export default function LoginPage({ setup, onDone }: { setup: boolean; onDone: (p: Profile) => void }) {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shake, setShake] = useState(0);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (setup && password !== repeat) {
      setError("تکرار رمز عبور یکسان نیست."); setShake((n) => n + 1);
      return;
    }
    setBusy(true);
    try {
      const body = setup ? { username: username.trim(), full_name: fullName.trim(), password } : { username: username.trim(), password };
      onDone(await authJson(setup ? "/setup" : "/login", { method: "POST", body: JSON.stringify(body) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "ورود ناموفق بود"); setShake((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };

  return <main className="login-page">
    <div className="login-orb a" /><div className="login-orb b" /><div className="login-orb c" />
    <form key={shake} className={`login-card${shake ? " shake" : ""}`} onSubmit={submit}>
      <div className="login-brand"><i>ا</i><div><b>اکسیر کادوس</b><small>مرکز فرماندهی مالی و فروش</small></div></div>
      <h1>{setup ? "ساخت مدیر سیستم" : "ورود به سامانه"}</h1>
      <p>{setup ? "اولین بار است که سامانه اجرا می‌شود. حساب مدیر سیستم را بسازید؛ بعد از آن کاربران دیگر و دسترسی ماژول‌هایشان را از «مدیریت کاربران» تعریف کنید."
        : "با نام کاربری و رمزی که مدیر سیستم برایتان تعریف کرده وارد شوید."}</p>
      {setup && <label>نام و نام خانوادگی<input value={fullName} onChange={(e) => setFullName(e.target.value)} required minLength={2} autoComplete="name" /></label>}
      <label>نام کاربری<input value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" dir="ltr" autoFocus /></label>
      <label>رمز عبور
        <span className="login-pass">
          <input type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={setup ? 6 : 1}
            autoComplete={setup ? "new-password" : "current-password"} dir="ltr" />
          <button type="button" onClick={() => setShow(!show)} aria-label={show ? "پنهان کردن رمز" : "نمایش رمز"}>{show ? "🙈" : "👁"}</button>
        </span>
      </label>
      {setup && <label>تکرار رمز عبور<input type={show ? "text" : "password"} value={repeat} onChange={(e) => setRepeat(e.target.value)} required minLength={6} autoComplete="new-password" dir="ltr" /></label>}
      {error && <div className="login-error" role="alert">{error}</div>}
      <button type="submit" className="login-submit" disabled={busy}>{busy ? <span className="login-spin" /> : setup ? "ساخت حساب و ورود" : "ورود"}</button>
    </form>
  </main>;
}

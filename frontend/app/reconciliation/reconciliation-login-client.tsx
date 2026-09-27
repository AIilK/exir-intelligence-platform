import { FormEvent, useState } from "react";

export default function ReconciliationLoginClient({ configured }: { configured: boolean }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(
    configured ? "" : "نام کاربری و رمز اپراتور هنوز در فایل تنظیمات تعریف نشده است.",
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!configured || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/reconciliation/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "ورود انجام نشد.");
      window.location.assign("/reconciliation");
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "ورود انجام نشد.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="rc-login">
      <form className="rc-login-card" onSubmit={submit}>
        <span className="rc-login-brand">EK</span>
        <h1>ورود به پنل مغایرت‌گیری</h1>
        <p>این بخش فقط در اختیار اپراتور تعیین‌شده خزانه قرار دارد.</p>
        <label>
          نام کاربری
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label>
          رمز عبور
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
        </label>
        {error && <div className="rc-error" role="alert">{error}</div>}
        <button className="rc-primary" disabled={!configured || busy}>
          {busy ? "در حال بررسی…" : "ورود امن"}
        </button>
        <div className="rc-login-note">Finance Command Center · دسترسی محدود</div>
      </form>
    </main>
  );
}

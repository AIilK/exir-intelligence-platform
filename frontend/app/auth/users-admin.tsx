"use client";
// مدیریت کاربران (فقط مدیر سیستم): تعریف نام کاربری/رمز، انتخاب ماژول‌های مجاز، غیرفعال‌سازی و حذف.
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { authJson, useAuth, type AppUser, type ModuleInfo } from "./auth";
import "./auth.css";

const when = (iso?: string | null) => {
  if (!iso) return "هنوز وارد نشده";
  try { return new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso)); } catch { return iso; }
};

/** ماژول‌ها به تفکیک دسته (مالی / فروش / سیستم)؛ هر دسته «همه / هیچ‌کدام» خودش را دارد. */
function ModulePicker({ catalog, value, onChange, disabled }: { catalog: ModuleInfo[]; value: string[]; onChange: (v: string[]) => void; disabled?: boolean }) {
  const toggle = (key: string) => onChange(value.includes(key) ? value.filter((k) => k !== key) : [...value, key]);
  const groups = Array.from(new Set(catalog.map((m) => m.group || "finance")));
  return <div className="ua-groups" style={disabled ? { opacity: .5, pointerEvents: "none" } : undefined}>
    {groups.map((g) => {
      const items = catalog.filter((m) => (m.group || "finance") === g);
      const all = items.every((m) => value.includes(m.key));
      return <div key={g} className="ua-group">
        <div className="ua-group-head"><b>{items[0]?.group_title || g}</b>
          <button type="button" className="ua-btn ghost" disabled={disabled}
            onClick={() => onChange(all ? value.filter((k) => !items.some((m) => m.key === k)) : Array.from(new Set([...value, ...items.map((m) => m.key)])))}>
            {all ? "هیچ‌کدام" : "همه"}</button></div>
        <div className="ua-mods">
          {items.map((m) => <label key={m.key} className={`ua-mod${value.includes(m.key) ? " on" : ""}`}>
            <input type="checkbox" checked={value.includes(m.key)} onChange={() => toggle(m.key)} disabled={disabled} />
            {value.includes(m.key) ? "✓" : "+"} {m.title}{m.has_alarms && <small>🔔</small>}
          </label>)}
        </div>
      </div>;
    })}
  </div>;
}

function UserRow({ u, catalog, me, reload }: { u: AppUser; catalog: ModuleInfo[]; me: number; reload: () => void }) {
  const [edit, setEdit] = useState(false);
  const [modules, setModules] = useState<string[]>(u.modules);
  const [fullName, setFullName] = useState(u.full_name);
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(u.is_admin);
  const [msg, setMsg] = useState<{ text: string; err?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const title = (key: string) => catalog.find((m) => m.key === key)?.title || key;

  const save = async (patch: Record<string, unknown>, done?: string) => {
    setBusy(true); setMsg(null);
    try {
      await authJson(`/users/${u.id}`, { method: "PATCH", body: JSON.stringify(patch) });
      setMsg({ text: done || "ذخیره شد." }); setPassword(""); reload();
    } catch (e) { setMsg({ text: e instanceof Error ? e.message : "خطا", err: true }); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm(`کاربر «${u.full_name}» و حافظه چت‌بات او حذف شود؟`)) return;
    try { await authJson(`/users/${u.id}`, { method: "DELETE" }); reload(); }
    catch (e) { setMsg({ text: e instanceof Error ? e.message : "خطا", err: true }); }
  };

  return <article className={`ua-user${u.is_active ? "" : " off"}`}>
    <header>
      <i>{u.full_name.slice(0, 1)}</i>
      <div><b>{u.full_name}</b> <small dir="ltr">@{u.username}</small><br /><small>آخرین ورود: {when(u.last_login_at)}</small></div>
      {u.is_admin && <span className="ua-tag admin">مدیر سیستم</span>}
      {!u.is_active && <span className="ua-tag off">غیرفعال</span>}
      {u.id === me && <span className="ua-tag">شما</span>}
      <div className="ua-row-actions">
        <button type="button" className="ua-btn ghost" onClick={() => setEdit(!edit)}>{edit ? "بستن" : "ویرایش و دسترسی"}</button>
        {u.id !== me && <button type="button" className="ua-btn ghost" disabled={busy} onClick={() => save({ is_active: !u.is_active }, u.is_active ? "غیرفعال شد." : "فعال شد.")}>{u.is_active ? "غیرفعال" : "فعال‌سازی"}</button>}
        {u.id !== me && <button type="button" className="ua-btn danger" onClick={remove}>حذف</button>}
      </div>
    </header>
    {!edit && <div className="ua-chips">{u.is_admin ? <span>همه ماژول‌ها</span> : u.modules.length ? u.modules.map((k) => <span key={k}>{title(k)}</span>) : <span>بدون ماژول</span>}</div>}
    {edit && <div>
      <div className="ua-form">
        <label>نام کامل<input value={fullName} onChange={(e) => setFullName(e.target.value)} /></label>
        <label>رمز جدید (اختیاری)<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="حداقل ۶ نویسه" dir="ltr" autoComplete="new-password" /></label>
        <label style={{ alignContent: "end" }}><span className={`ua-mod${isAdmin ? " on" : ""}`} onClick={() => u.id !== me && setIsAdmin(!isAdmin)}>
          {isAdmin ? "✓" : "+"} مدیر سیستم (همه ماژول‌ها + مدیریت کاربران)</span></label>
      </div>
      <ModulePicker catalog={catalog} value={modules} onChange={setModules} disabled={isAdmin} />
      <div className="ua-row-actions">
        <button type="button" className="ua-btn" disabled={busy} onClick={() => save({ full_name: fullName, modules, is_admin: isAdmin, ...(password ? { password } : {}) })}>ذخیره تغییرات</button>
        {msg && <span className={`ua-msg${msg.err ? " err" : ""}`}>{msg.text}</span>}
      </div>
    </div>}
    {!edit && msg && <span className={`ua-msg${msg.err ? " err" : ""}`}>{msg.text}</span>}
  </article>;
}

export default function UsersAdmin() {
  const { profile } = useAuth();
  const [users, setUsers] = useState<AppUser[] | null>(null);
  const [catalog, setCatalog] = useState<ModuleInfo[]>(profile.catalog);
  const [form, setForm] = useState({ username: "", full_name: "", password: "" });
  // دستیار هوشمند پیش‌فرض روشن است؛ داده‌ای که جواب می‌دهد به همان ماژول‌های تیک‌خورده محدود است.
  const [modules, setModules] = useState<string[]>(["chatbot"]);
  const [msg, setMsg] = useState<{ text: string; err?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    authJson("/users").then((j) => { setUsers(j.users); setCatalog(j.modules); }).catch((e) => setMsg({ text: e.message, err: true }));
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      const u = await authJson("/users", { method: "POST", body: JSON.stringify({ ...form, modules }) });
      setMsg({ text: `کاربر «${u.full_name}» ساخته شد؛ با نام کاربری ${u.username} وارد می‌شود.` });
      setForm({ username: "", full_name: "", password: "" }); setModules(["chatbot"]); load();
    } catch (err) { setMsg({ text: err instanceof Error ? err.message : "خطا", err: true }); }
    finally { setBusy(false); }
  };

  return <section className="ua">
    <form className="ua-card" onSubmit={create}>
      <h3>تعریف کاربر جدید</h3>
      <p>نام کاربری و رمز را اینجا بسازید و ماژول‌هایی را که این شخص می‌بیند تیک بزنید. هر کاربر فقط صفحه‌ها، الارم‌ها و پاسخ‌های چت‌بات همان ماژول‌ها را می‌گیرد. «دستیار هوشمند» در دسته سیستم اجازه استفاده از چت‌بات است.</p>
      <div className="ua-form">
        <label>نام و نام خانوادگی<input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required minLength={2} /></label>
        <label>نام کاربری (انگلیسی)<input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required minLength={3} pattern="[A-Za-z0-9_.\-]+" dir="ltr" autoComplete="off" /></label>
        <label>رمز عبور<input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={6} dir="ltr" autoComplete="new-password" /></label>
      </div>
      <ModulePicker catalog={catalog} value={modules} onChange={setModules} />
      <div className="ua-row-actions">
        <button type="submit" className="ua-btn" disabled={busy}>{busy ? "در حال ساخت…" : "ساخت کاربر"}</button>
        {msg && <span className={`ua-msg${msg.err ? " err" : ""}`}>{msg.text}</span>}
      </div>
    </form>
    <div className="ua-card">
      <h3>کاربران ({users ? users.length.toLocaleString("fa-IR") : "…"})</h3>
      <p>برای تغییر ماژول‌ها یا رمز روی «ویرایش و دسترسی» بزنید. با تغییر رمز یا غیرفعال کردن، نشست‌های باز آن شخص بسته می‌شود.</p>
      <div className="ua-list">
        {(users || []).map((u) => <UserRow key={`${u.id}-${u.modules.join()}-${u.is_admin}-${u.is_active}`} u={u} catalog={catalog} me={profile.user.id} reload={load} />)}
      </div>
    </div>
  </section>;
}

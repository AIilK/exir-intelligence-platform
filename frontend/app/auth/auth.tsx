"use client";
// ورود کاربران و سطح دسترسی (Backend: backend/app/auth).
// نشست با کوکی HttpOnly بک‌اند است؛ installAuthFetch همه درخواست‌های /api/v1 را با credentials می‌فرستد
// و با پاسخ ۴۰۱ کاربر را به صفحه ورود برمی‌گرداند.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import LoginPage from "./login-page";
import { applyLook } from "../theme/theme";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
export const AUTH_API = () => `http://${apiHost()}:8000/api/v1/auth`;

export type ModuleInfo = { key: string; title: string; views: string[]; has_alarms: boolean; group?: string; group_title?: string };
export type AppUser = {
  id: number; username: string; full_name: string; is_admin: boolean; is_active: boolean;
  modules: string[]; preferences: Preferences; last_login_at?: string | null;
};
/** تم، والپیپر و حیوان خانگی هر کاربر (روی سرور ذخیره می‌شود) */
export type Preferences = { theme?: string; wallpaper?: string; pet?: string; pet_name?: string };
export type Profile = { user: AppUser; modules: string[]; views: string[]; catalog: ModuleInfo[] };

let installed = false;
export function installAuthFetch() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const isApi = url.includes("/api/v1/");
    const response = await original(input, isApi ? { ...init, credentials: "include" } : init);
    if (isApi && response.status === 401 && !url.includes("/api/v1/auth/")) window.dispatchEvent(new Event("exir:unauthorized"));
    return response;
  };
}

export async function authJson(path: string, options?: RequestInit) {
  const r = await fetch(`${AUTH_API()}${path}`, {
    ...options, headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = j.detail;
    throw Error(typeof d === "string" ? d : Array.isArray(d) ? "اطلاعات واردشده معتبر نیست (نام کاربری فقط حروف انگلیسی/عدد، رمز حداقل ۶ نویسه)." : `خطای ${r.status}`);
  }
  return j;
}

type AuthValue = {
  profile: Profile;
  can: (view: string) => boolean;
  hasModule: (key: string) => boolean;
  logout: () => Promise<void>;
  setPreferences: (prefs: Preferences) => void;
};
const AuthContext = createContext<AuthValue | null>(null);
export const useAuth = () => {
  const v = useContext(AuthContext);
  if (!v) throw Error("useAuth outside AuthGate");
  return v;
};

/** تا وقتی کاربر وارد نشده صفحه ورود (یا ساخت اولین مدیر) را نشان می‌دهد.
 *  screenClass: کلاسی که دور صفحه ورود/انتظار می‌آید (داشبورد یکپارچه استایل مالی را زیر .fin-scope دارد). */
export default function AuthGate({ children, screenClass }: { children: ReactNode; screenClass?: string }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [state, setState] = useState<"loading" | "login" | "setup" | "ready" | "offline">("loading");

  const check = useCallback(async () => {
    try {
      const me = await fetch(`${AUTH_API()}/me`);
      if (me.ok) {
        const p: Profile = await me.json();
        setProfile(p); applyLook(p.user.preferences); setState("ready");
        return;
      }
      const s = await authJson("/status");
      if (!s.auth_enabled) {
        setState("offline");
        return;
      }
      setState(s.needs_setup ? "setup" : "login");
    } catch {
      setState("offline");
    }
  }, []);
  useEffect(() => { void check(); }, [check]);
  useEffect(() => {
    const onUnauthorized = () => { setProfile(null); setState((s) => (s === "ready" ? "login" : s)); };
    window.addEventListener("exir:unauthorized", onUnauthorized);
    return () => window.removeEventListener("exir:unauthorized", onUnauthorized);
  }, []);

  const logout = useCallback(async () => {
    await authJson("/logout", { method: "POST" }).catch(() => undefined);
    setProfile(null); applyLook({}); setState("login");
  }, []);
  // ذخیره با کمی تأخیر: چند انتخاب پشت‌سرهم فقط یک درخواست (آخرین انتخاب) می‌فرستند و ترتیبشان به هم نمی‌خورد.
  const saveTimer = useRef<number | null>(null);
  const pendingPrefs = useRef<Preferences>({});
  const setPreferences = useCallback((prefs: Preferences) => {
    setProfile((p) => (p ? { ...p, user: { ...p.user, preferences: { ...p.user.preferences, ...prefs } } } : p));
    pendingPrefs.current = { ...pendingPrefs.current, ...prefs };
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      const body = pendingPrefs.current;
      pendingPrefs.current = {};
      authJson("/me/preferences", { method: "PATCH", body: JSON.stringify(body) }).catch(() => undefined);
    }, 500);
  }, []);

  const screen = (node: ReactNode) => (screenClass ? <div className={screenClass}>{node}</div> : node);
  if (state === "loading") return screen(<div className="auth-splash"><i /><span>در حال آماده‌سازی…</span></div>);
  if (state === "offline") return screen(<div className="auth-splash error"><b>اتصال به سرور برقرار نشد</b>
    <span>بک‌اند مالی (FastAPI) باید در حال اجرا باشد.</span><button type="button" onClick={() => { setState("loading"); void check(); }}>تلاش دوباره</button></div>);
  if (state !== "ready" || !profile) {
    return screen(<LoginPage setup={state === "setup"} onDone={(p) => { setProfile(p); applyLook(p.user.preferences); setState("ready"); }} />);
  }
  const value: AuthValue = {
    profile,
    can: (view) => profile.user.is_admin || profile.views.includes(view),
    hasModule: (key) => profile.user.is_admin || profile.modules.includes(key),
    logout, setPreferences,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

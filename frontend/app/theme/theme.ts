// تم رنگی و والپیپر هر کاربر: روی <html> با data-theme / data-wallpaper اعمال می‌شود (استایل‌ها در theme.css)
// و برای هر کاربر در بک‌اند (preferences) ذخیره می‌شود.

export type Look = { theme?: string; wallpaper?: string };

export const THEMES: { key: string; label: string; colors: [string, string] }[] = [
  { key: "teal", label: "فیروزه‌ای", colors: ["#2dd4bf", "#0f766e"] },
  { key: "ocean", label: "اقیانوسی", colors: ["#38bdf8", "#1d4ed8"] },
  { key: "violet", label: "بنفش", colors: ["#a78bfa", "#6d28d9"] },
  { key: "rose", label: "صورتی", colors: ["#fb7185", "#be185d"] },
  { key: "sunset", label: "غروب", colors: ["#fbbf24", "#ea580c"] },
  { key: "emerald", label: "زمردی", colors: ["#4ade80", "#15803d"] },
  { key: "rainbow", label: "رنگین‌کمان", colors: ["#f472b6", "#60a5fa"] },
];

export const WALLPAPERS: { key: string; label: string; preview: string }[] = [
  { key: "none", label: "ساده", preview: "linear-gradient(160deg,#07131f,#091925)" },
  { key: "aurora", label: "شفق قطبی", preview: "linear-gradient(135deg,#052e2b,#0b3b5e 45%,#3b0764)" },
  { key: "nebula", label: "کهکشان", preview: "radial-gradient(circle at 30% 30%,#7c3aed,transparent 45%),radial-gradient(circle at 70% 70%,#db2777,transparent 45%),#0b0820" },
  { key: "ocean", label: "اقیانوس", preview: "linear-gradient(180deg,#0c4a6e,#082f49 60%,#020617)" },
  { key: "sunset", label: "غروب", preview: "linear-gradient(160deg,#7c2d12,#9d174d 50%,#1e1b4b)" },
  { key: "forest", label: "جنگل", preview: "linear-gradient(160deg,#14532d,#052e16 60%,#020d08)" },
  { key: "grid", label: "شبکه", preview: "linear-gradient(#1e3a5f 1px,transparent 1px) 0 0/14px 14px,linear-gradient(90deg,#1e3a5f 1px,transparent 1px) 0 0/14px 14px,#071422" },
  { key: "dots", label: "نقطه‌ها", preview: "radial-gradient(#2dd4bf55 1.2px,transparent 1.4px) 0 0/12px 12px,#07131f" },
];

export function applyLook(look: Look) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const theme = THEMES.some((t) => t.key === look.theme) ? look.theme! : "teal";
  const wallpaper = WALLPAPERS.some((w) => w.key === look.wallpaper) ? look.wallpaper! : "none";
  root.dataset.theme = theme;
  root.dataset.wallpaper = wallpaper;
}

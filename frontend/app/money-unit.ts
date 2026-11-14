// واحد نمایش مبلغ برای کل برنامه (کلید بالای داشبورد یکپارچه): خودکار / تومان / میلیون تومان / میلیارد تومان.
// «خودکار» همان رفتار قبلی است: هر عدد بسته به بزرگی‌اش میلیون یا میلیارد نشان داده می‌شود.
// همه قالب‌بندهای مبلغ (shortToman صفحه‌های مالی، money/mt داشبورد یکپارچه) از همین‌جا می‌خوانند؛ مبالغ ورودی ریال‌اند.
export type MoneyUnit = "auto" | "toman" | "million" | "billion";

const KEY = "exir.unit";
export const MONEY_UNITS: { key: MoneyUnit; label: string }[] = [
  { key: "auto", label: "خودکار" },
  { key: "toman", label: "تومان" },
  { key: "million", label: "میلیون" },
  { key: "billion", label: "میلیارد" },
];

export function getMoneyUnit(): MoneyUnit {
  try {
    const u = localStorage.getItem(KEY);
    if (u === "toman" || u === "million" || u === "billion") return u;
  } catch { /* بدون localStorage (SSR یا حالت خصوصی) */ }
  return "auto";
}

export function setMoneyUnit(unit: MoneyUnit): void {
  try { localStorage.setItem(KEY, unit); } catch { /* حالت خصوصی */ }
}

const nf0 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 });

/** ریال ← {v: عدد، u: واحد بدون «تومان»}؛ در واحد «تومان» u خالی است. */
export function moneyParts(rial: number | null | undefined): { v: string; u: string } {
  const t = Number(rial || 0) / 10, a = Math.abs(t), unit = getMoneyUnit();
  if (unit === "toman") return { v: nf0.format(t), u: "" };
  if (unit === "million") return { v: (a >= 1e8 ? nf0 : nf1).format(t / 1e6), u: "میلیون" };
  if (unit === "billion") return { v: (a >= 1e11 ? nf1 : nf2).format(t / 1e9), u: "میلیارد" };
  if (a >= 1e9) return { v: nf1.format(t / 1e9), u: "میلیارد" };
  if (a >= 1e6) return { v: nf0.format(t / 1e6), u: "میلیون" };
  return { v: nf0.format(t), u: "" };
}

/** ریال ← «۱۲٫۳ میلیارد» / «۸۵۰ میلیون» / «۱۲٬۳۴۵» (به تومان؛ کلمه «تومان» را صفحه خودش می‌نویسد) */
export function shortTomanText(rial: number | null | undefined): string {
  const { v, u } = moneyParts(rial);
  return u ? `${v} ${u}` : v;
}

/** ستون‌های جدول که قبلاً همیشه «میلیون تومان» بودند: عدد و عنوان واحد ستون */
export function tableMoney(rial: number): string {
  const unit = getMoneyUnit();
  if (unit === "toman") return nf0.format(rial / 10);
  if (unit === "billion") return nf2.format(rial / 1e10);
  return nf0.format(rial / 1e7);
}
export function tableMoneyLabel(): string {
  const unit = getMoneyUnit();
  return unit === "toman" ? "تومان" : unit === "billion" ? "میلیارد تومان" : "میلیون تومان";
}

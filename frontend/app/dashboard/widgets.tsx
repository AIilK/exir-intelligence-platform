// اجزای کوچک مشترک داشبورد مالی: کارت عدد (K)، تیتر بخش، برچسب ریسک و وضعیت.
import { menu, openInsight } from "./shared";
import type { InsightPayload, View } from "./types";

export function K({
  t,
  v,
  n,
  c,
  detail,
}: {
  t: string;
  v: string;
  n: string;
  c: string;
  detail?: InsightPayload;
}) {
  return (
    <button
      type="button"
      className={`fd-kpi ${c} drillable`}
      onClick={() =>
        openInsight(
          detail || {
            title: t,
            tone: c,
            subtitle: "آمار شاخص انتخاب‌شده",
            stats: [
              { label: "مقدار فعلی", value: v },
              { label: "توضیح / واحد", value: n },
            ],
          },
        )
      }
    >
      <small>{t}</small>
      <b>{v}</b>
      <em>{n}</em>
    </button>
  );
}
export function Heading({ h, p }: { h: string; p: string }) {
  return (
    <div className="fd-heading">
      <h2>{h}</h2>
      <p>{p}</p>
    </div>
  );
}
export function Risk({ x }: { x: string }) {
  return (
    <span className={`fd-badge ${x}`}>
      {x === "critical" ? "بحرانی" : x === "danger" ? "نیازمند توجه" : "مناسب"}
    </span>
  );
}
export function Status({ x }: { x: string }) {
  return (
    <span className={`management-status ${x}`}>
      {x === "critical" ? "بحرانی" : x === "healthy" ? "مناسب" : "نیازمند توجه"}
    </span>
  );
}
export function label(v: View) {
  return v === "receivedCheques"
    ? "چک‌های دریافتی"
    : v === "issuedCheques"
      ? "چک‌های پرداختی / صادرشده"
      : menu.find((x) => x[0] === v)?.[2] || v;
}
export function description(v: View) {
  return (
    {
      overview: "ترکیب خلاصه مدیریتی مالی و فروش، با تصمیم‌های امروز و رتبه هیبریدها",
      management: "چک‌ها، پرداخت تجاری، نقدینگی و توزیع بار در یک نگاه",
      sales: "فروش خالص ماه و سال، هیبریدها، توزیع و وصول و شبکه فروش کارآمد در یک نگاه",
      users: "تعریف کاربر، نام کاربری و رمز، و ماژول‌هایی که هر شخص می‌بیند",
      customers: "خرید، ویزیتور، مطالبات، چک‌ها و احتمال برگشت هر مشتری",
      cheques: "انتخاب جریان دریافتی یا پرداختی و ورود از خلاصه به جزئیات",
      payables: "حساب‌های پرداختنی تجاری (۵۱۱۰۰۲) و غیرتجاری (۵۱۲۰۰۱) راهکاران؛ با کلیک روی هر طرف حساب ریز گردشش باز می‌شود",
      pnl: "سود و زیان سه کانال (هیبرید، B2B، صادرات): لایو از SQL راهکاران و کارآمد، با مقایسه فایل‌های اکسل مالی",
      purchaseDocs: "زنده از راهکاران: اسناد خرید ثبت‌حسابداری‌نشده (عملیات گروهی اسناد) و مرور تدارکات با تطبیق رسید موقت و دائم",
      inventoryPricing: "اسناد انبار راهکاران که کالایشان ثبت شده ولی قیمت‌گذاری نشده‌اند — به تفکیک انبار کارخانه",
      cashBank:
        "ریز دریافت و پرداخت نقدی و بانکی، حواله‌ها و انتقال‌های داخلی همراه Agent مستقل",
      receivedCheques: "مطالبات، وصول، ریسک و سررسید چک‌های دریافتی",
      issuedCheques: "تعهدات و سررسید چک‌های پرداختی و صادرشده",
      collections: "مسئول، مهلت، تماس، قول پرداخت و نتیجه پیگیری",
      distribution: "فاکتورهای توزیع‌نشده، سرعت خروج بار و عملکرد موزعان — کارآمد",
      representatives: "کیفیت پرتفوی و وصول به تفکیک نماینده",
      alerts: "الارم‌های فعال ماژول‌های شما با سطح اهمیت و اقدام پیشنهادی",
      history: "روند تغییر گزارش‌های مدیریتی در طول زمان",
      performance: "مقایسه پیش‌بینی‌ها با نتایج واقعی",
      settings: "مدیریت آستانه‌ها و زمان اجرای اتوماسیون",
      whatsapp: "ارسال خودکار بدهی مشتری، چک‌های پیش‌رو و اکسل ویزیتورها با واتساپ، در روز و ساعت مشخص",
    } as Record<View, string>
  )[v];
}

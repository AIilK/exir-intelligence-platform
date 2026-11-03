"use client";
// نمایش مشترک چک‌ها در همه جداول:
// - chequeNo: شماره چک به صورت متن (رقم فارسی، بدون جداکننده هزارگان و بدون حذف صفر اول).
// - RegCell: «ثبت در سیستم» = تاریخ (و برای راهکاران ساعت) ثبت چک + کاربری که ثبت کرده؛ از فیلدهای
//   registered_at_jalali / registered_by که Backend به هر ردیف چک اضافه می‌کند.

const toFa = (v: string) => v.replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);

export function chequeNo(value: unknown): string {
  const s = String(value ?? "").trim();
  return s ? toFa(s) : "—";
}

export function RegCell({ x, fallback }: { x: any; fallback?: string | null }) {
  const at = x?.registered_at_jalali || fallback;
  if (!at) return <span className="reg-cell">—</span>;
  return <span className="reg-cell" title={x?.registered_by ? `ثبت توسط ${x.registered_by}` : undefined}>
    <b>{toFa(String(at))}</b>
    {x?.registered_by && <small>👤 {x.registered_by}</small>}
  </span>;
}

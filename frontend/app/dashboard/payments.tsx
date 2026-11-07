// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (payments).
import { useEffect, useState } from "react";
import { K } from "./widgets";
import { fa, fullToman, treasuryRequest } from "./shared";

export function CompanyPaymentOrders() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("همه");
  const [state, setState] = useState("همه");
  const [method, setMethod] = useState("همه");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [monthsBack, setMonthsBack] = useState("همه");
  const [source, setSource] = useState<"all" | "rahkaran" | "karamad">("all");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setState("همه"); setCategory("همه");
    treasuryRequest(`/payment-orders/company?limit=5000&source=${source}`)
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "خطا در دریافت حواله‌ها"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [source]);
  const sourceLabel = source === "rahkaran" ? "راهکاران" : source === "karamad" ? "کارآمد" : "راهکاران و کارآمد";
  const rows = data?.rows || [];
  const categories = ["همه", ...Array.from(new Set(rows.map((x:any) => x.category))).filter(Boolean)] as string[];
  const states = ["همه", ...Array.from(new Set(rows.map((x:any) => String(x.state)))).filter(Boolean)] as string[];
  const paymentOrderStateFa = (value:any) => {
    const code = String(value ?? "");
    const labels: Record<string,string> = {
      "1": "در انتظار تأیید",
      "2": "تأییدشده",
      "4": "وضعیت نهایی",
      "5": "وضعیت نهایی",
    };
    return labels[code] || (code ? `وضعیت ${fa(code)}` : "نامشخص");
  };
  const stateLabels = new Map<string, string>(rows.filter((x:any) => x.state_label && x.source === "karamad").map((x:any) => [String(x.state), x.state_label]));
  const stateFa = (value:any) => stateLabels.get(String(value)) || paymentOrderStateFa(value);
  const viewRows = rows.filter((x:any) => {
    const q = search.trim().toLowerCase();
    const hay = `${x.payment_order_number || ""} ${x.counterpart_name || ""} ${x.counterpart_code || ""} ${x.description || ""} ${x.bank_name || ""} ${x.registered_by || ""}`.toLowerCase();
    const orderDate = String(x.order_date || "").slice(0,10);
    let monthsOk = true;
    if (monthsBack !== "همه" && orderDate) {
      const d = new Date(`${orderDate}T00:00:00`);
      const cutoff = new Date();
      cutoff.setHours(0,0,0,0);
      cutoff.setMonth(cutoff.getMonth() - Number(monthsBack));
      monthsOk = d >= cutoff;
    }
    const dateOk = (!dateFrom || (orderDate && orderDate >= dateFrom)) && (!dateTo || (orderDate && orderDate <= dateTo));
    return (!q || hay.includes(q)) && (category === "همه" || x.category === category) &&
      (state === "همه" || String(x.state) === state) && (method === "همه" || x.payment_method === method) && dateOk && monthsOk;
  });
  const filteredAmount = viewRows.reduce((a:number,x:any)=>a+Number(x.calculated_amount||0),0);
  const filteredApproved = viewRows.filter((x:any) => Boolean(x.approve_date)).length;
  const filteredWaiting = viewRows.filter((x:any) => !x.approve_date).length;
  const filteredBankCash = viewRows.filter((x:any) => x.payment_method === "نقد/بانکی" || x.payment_method === "ترکیبی").length;
  const filteredCheque = viewRows.filter((x:any) => Number(x.cheque_amount || 0) > 0).length;
  const filteredCategories = viewRows.reduce((acc:Record<string,{count:number,amount:number}>, x:any) => {
    const key = x.category || "سایر";
    if (!acc[key]) acc[key] = {count:0, amount:0};
    acc[key].count += 1;
    acc[key].amount += Number(x.calculated_amount || 0);
    return acc;
  }, {});
  return <section className="company-payments-page">
    <div className="section-head"><div><small>{source === "karamad" ? "KARAMAD · tblDraftP / tblCashP / tblChequeP" : source === "rahkaran" ? "RAHKARAN · RPA3.PaymentOrder" : "RAHKARAN + KARAMAD"}</small><h2>حواله‌های پرداختی شرکت</h2><p>نمای یکپارچه پرداخت‌های {sourceLabel} با تفکیک طرف حساب، دسته، وضعیت و روش پرداخت.</p></div></div>
    {error && <div className="fd-errors"><span>{error}</span></div>}
    {(data?.errors || []).map((m:string) => <div key={m} className="fd-errors"><span>{m}</span></div>)}
    {loading ? <div className="panel">در حال دریافت پرداخت‌های {sourceLabel}…</div> : <>
      <div className="company-payment-kpis">
        <K t="کل حواله‌ها" v={fa(viewRows.length)} n="مطابق فیلتر فعلی" c="blue" />
        <K t="مبلغ کل" v={fullToman(filteredAmount)} n="تومان · مطابق فیلتر فعلی" c="teal" />
        <K t={source === "karamad" ? "سند حسابداری صادر شده" : "دارای تاریخ تأیید"} v={fa(filteredApproved)} n={source === "rahkaran" ? "مطابق فیلتر فعلی" : "کارآمد: صدور سند حسابداری"} c="green" />
        <K t={source === "karamad" ? "بدون سند حسابداری" : "در انتظار تأیید"} v={fa(filteredWaiting)} n="مطابق فیلتر فعلی" c="amber" />
        <K t="نقد / بانکی" v={fa(filteredBankCash)} n="تعداد حواله در فیلتر فعلی" c="blue" />
        <K t="چکی" v={fa(filteredCheque)} n="تعداد حواله در فیلتر فعلی" c="red" />
      </div>
      <div className="company-payment-categories">
        {Object.entries(filteredCategories).map(([name, v]:any) => <button key={name} className={category===name?"active":""} onClick={()=>setCategory(category===name?"همه":name)}><span>{name}</span><b>{fa(v.count)}</b><small>{fullToman(Number(v.amount||0))} تومان</small></button>)}
      </div>
      <div className="company-payment-filters">
        <select value={source} onChange={e=>setSource(e.target.value as "all" | "rahkaran" | "karamad")} aria-label="منبع داده" title="منبع داده">
          <option value="all">راهکاران + کارآمد</option>
          <option value="rahkaran">فقط راهکاران</option>
          <option value="karamad">فقط کارآمد</option>
        </select>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="جستجو: شماره حواله، طرف حساب، شرح، بانک…" />
        <select value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(x=><option key={x}>{x}</option>)}</select>
        <select value={state} onChange={e=>setState(e.target.value)}>{states.map(x=><option key={x} value={x}>{x==="همه"?"همه وضعیت‌ها":stateFa(x)}</option>)}</select>
        <select value={monthsBack} onChange={e=>setMonthsBack(e.target.value)} aria-label="بازه چندماهه" title="بازه چندماهه">
          <option value="همه">همه بازه‌ها</option>
          <option value="1">۱ ماه اخیر</option>
          <option value="2">۲ ماه اخیر</option>
          <option value="3">۳ ماه اخیر</option>
          <option value="6">۶ ماه اخیر</option>
          <option value="12">۱۲ ماه اخیر</option>
          <option value="24">۲۴ ماه اخیر</option>
        </select>
        <input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)} aria-label="از تاریخ" title="از تاریخ" />
        <input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)} aria-label="تا تاریخ" title="تا تاریخ" />
        <select value={method} onChange={e=>setMethod(e.target.value)}>{["همه","نقد/بانکی","چکی","ترکیبی","نامشخص"].map(x=><option key={x}>{x}</option>)}</select>
      </div>
      <div className="company-payment-filter-summary"><b>{fa(viewRows.length)} حواله</b><span>{fullToman(filteredAmount)} تومان در فیلتر فعلی</span></div>
      <div className="table-wrap"><table><thead><tr><th>تاریخ</th><th>منبع</th><th>شماره حواله</th><th>طرف حساب</th><th>دسته</th><th>وضعیت</th><th>روش</th><th>بانکی</th><th>نقد</th><th>چک</th><th>مبلغ</th><th>شرح</th></tr></thead><tbody>
        {viewRows.map((x:any)=><tr key={x.payment_order_id}><td>{x.order_date_jalali || x.order_date?.slice(0,10) || "—"}</td><td><span className={`payment-source-chip ${x.source || "rahkaran"}`}>{x.source_label || "راهکاران"}</span></td><td><b>{x.payment_order_number}</b>{x.payment_kind_label && <small className="payment-subline">{x.payment_kind_label}</small>}</td><td>{x.counterpart_name || `#${x.counterpart_ref || "—"}`}{(x.bank_name || x.registered_by) && <small className="payment-subline">{[x.bank_name, x.registered_by && `ثبت: ${x.registered_by}`].filter(Boolean).join(" • ")}</small>}</td><td><span className="payment-category-chip">{x.category}</span></td><td>{x.source === "karamad" ? x.state_label : paymentOrderStateFa(x.state)}</td><td>{x.payment_method}</td><td>{fullToman(Number(x.deposit_amount||0))}</td><td>{fullToman(Number(x.cash_amount||0))}</td><td>{fullToman(Number(x.cheque_amount||0))}</td><td><b>{fullToman(Number(x.calculated_amount||0))}</b></td><td className="payment-description">{x.description || "—"}</td></tr>)}
      </tbody></table></div>
      <p className="company-payment-note">دسته‌بندی فعلی مدیریتی و مبتنی بر شرح حواله است. وضعیت‌های ۴ و ۵ راهکاران هر دو به‌عنوان «وضعیت نهایی» نمایش داده می‌شوند. در کارآمد هر سند پرداخت (حواله بانکی، پرداخت نقدی صندوق، چک پرداختی) یک ردیف است؛ کارآمد تاریخ تأیید ندارد و «صدور سند حسابداری» به‌جای تأیید آمده، و دسته از روی تفصیلی طرف حساب تعیین می‌شود. فیلتر چندماهه نیز در کنار بازه تاریخ دستی قابل استفاده است.</p>
    </>}
  </section>;
}

// view / onViewChange: داشبورد یکپارچه (unified/) صفحه را از منوی خودش انتخاب می‌کند؛ بدون آن‌ها صفحه خودش view را نگه می‌دارد.

"use client";

import { DragEvent, useMemo, useRef, useState } from "react";

type BusinessCounts = {
  posted?: number;
  reversed?: number;
  internal_transfer?: number;
  needs_review?: number;
  unposted?: number;
};

type ReconciliationReport = {
  reconciliation_id: string;
  file?: { filename?: string; sheet_name?: string };
  bank_account?: { display_label?: string; bank_name?: string };
  account?: { display_label?: string; bank_name?: string };
  summary?: {
    bank_row_count?: number;
    definite_resolution_rate?: number;
    business_counts?: BusinessCounts;
  };
  book_balance?: {
    available?: boolean;
    message?: string;
    matched_day_count?: number;
    day_count?: number;
    last_matched_date_jalali?: string | null;
    first_unmatched_date_jalali?: string | null;
  };
};

function balanceStatus(report: ReconciliationReport): string {
  const balance = report.book_balance;
  if (!balance) return "";
  if (!balance.available) return balance.message ?? "";
  const days = `${toFa(balance.matched_day_count)} از ${toFa(balance.day_count)} روز`;
  if (!balance.first_unmatched_date_jalali) {
    return `مانده پایان روز بانک و دفتر راهکاران در همه روزها برابر است (${days}).`;
  }
  return `مانده بانک و دفتر راهکاران تا ${balance.last_matched_date_jalali ?? "-"} برابر است؛ اولین روز مغایر ${balance.first_unmatched_date_jalali} (${days} برابر).`;
}

const ACCEPTED_EXTENSIONS = [".xlsx", ".xls", ".csv", ".pdf", ".html", ".htm"];

function acceptedFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension));
}

function toFa(value: number | undefined): string {
  return Number(value ?? 0).toLocaleString("fa-IR");
}

function percent(value: number | undefined): string {
  return `${Math.round(Number(value ?? 0) * 100).toLocaleString("fa-IR")}٪`;
}

export default function ReconciliationClient({
  displayName,
  signOutPath,
}: {
  displayName: string;
  signOutPath: string | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<ReconciliationReport | null>(null);

  const counts = report?.summary?.business_counts ?? {};
  const accountLabel = useMemo(
    () =>
      report?.bank_account?.display_label ??
      report?.account?.display_label ??
      "حساب بانکی شناسایی‌شده",
    [report],
  );

  const chooseFile = (selected?: File) => {
    if (!selected) return;
    setError("");
    setReport(null);
    if (!acceptedFile(selected)) {
      setFile(null);
      setError("فایل‌های Excel، CSV، PDF یا HTML صورتحساب بانکی قابل بارگذاری هستند.");
      return;
    }
    setFile(selected);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0]);
  };

  const upload = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch("/__reconciliation_proxy/reconciliation/auto-upload", {
        method: "POST",
        body,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "پردازش فایل با خطا مواجه شد.");
      }
      setReport(payload);
    } catch (uploadError) {
      const message = uploadError instanceof Error ? uploadError.message : "";
      setError(
        message === "Failed to fetch" || message === "Load failed"
          ? "اتصال مستقیم به سرویس مغایرت‌گیری برقرار نشد. فایل از Proxy داخلی پورت 3000 به Backend ارسال می‌شود؛ اجرای Frontend را بعد از اعمال تنظیمات جدید دوباره راه‌اندازی کنید."
          : message || "پردازش فایل با خطا مواجه شد.",
      );
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setFile(null);
    setReport(null);
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const signOut = async () => {
    if (signOutPath) {
      window.location.assign(signOutPath);
      return;
    }
    await fetch("/api/reconciliation/session", { method: "DELETE" });
    window.location.assign("/reconciliation/login");
  };

  return (
    <main className="rc-shell">
      <header className="rc-header">
        <div className="rc-brand">
          <span>EK</span>
          <div>
            <strong>اکسیر کادوس</strong>
            <small>پنل مستقل خزانه</small>
          </div>
        </div>
        <div className="rc-user">
          <div>
            <strong>{displayName}</strong>
            <small>اپراتور مغایرت‌گیری</small>
          </div>
          <button type="button" onClick={signOut}>خروج امن</button>
        </div>
      </header>

      <section className="rc-intro">
        <div>
          <span className="rc-pill">مغایرت‌گیری بانک</span>
          <h1>صورتحساب را وارد کنید؛ خروجی آماده را تحویل بگیرید.</h1>
          <p>
            بانک، حساب و ستون‌ها به‌صورت خودکار شناسایی می‌شوند. برای بانک ملت PDF و HTML خروجی اینترنت‌بانک هم قابل پردازش است. فایل اصلی ذخیره
            نمی‌شود و نتیجه فقط برای بررسی انسانی آماده خواهد شد.
          </p>
        </div>
        <ol className="rc-steps" aria-label="مراحل مغایرت‌گیری">
          <li className={file ? "done" : "active"}><b>۱</b><span>انتخاب فایل</span></li>
          <li className={busy ? "active" : report ? "done" : ""}><b>۲</b><span>پردازش</span></li>
          <li className={report ? "active" : ""}><b>۳</b><span>دریافت خروجی</span></li>
        </ol>
      </section>

      {!report ? (
        <section className="rc-workspace">
          <div
            className={`rc-dropzone ${dragging ? "dragging" : ""} ${file ? "selected" : ""}`}
            onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xls,.csv,.pdf,.html,.htm"
              onChange={(event) => chooseFile(event.target.files?.[0])}
            />
            <span className="rc-file-icon">{file ? "✓" : "⇧"}</span>
            <h2>{file ? file.name : "فایل صورتحساب بانک را اینجا رها کنید"}</h2>
            <p>
              {file
                ? `${(file.size / 1024 / 1024).toLocaleString("fa-IR", { maximumFractionDigits: 2 })} مگابایت · آماده پردازش`
                : "یا برای انتخاب فایل کلیک کنید · Excel، CSV، PDF یا HTML"}
            </p>
            {file && <button type="button" onClick={(event) => { event.stopPropagation(); reset(); }}>تغییر فایل</button>}
          </div>

          <aside className="rc-note">
            <span>✓</span>
            <div>
              <strong>پردازش کنترل‌شده و فقط‌خواندنی</strong>
              <p>هیچ سندی در راهکاران ثبت یا ویرایش نمی‌شود.</p>
            </div>
          </aside>

          {error && <div className="rc-error" role="alert">{error}</div>}
          <button className="rc-primary" disabled={!file || busy} onClick={upload}>
            {busy ? <><i /> در حال تطبیق با راهکاران…</> : "شروع مغایرت‌گیری"}
          </button>
        </section>
      ) : (
        <section className="rc-result">
          <header>
            <div className="rc-success">✓</div>
            <div>
              <span>پردازش با موفقیت انجام شد</span>
              <h2>{accountLabel}</h2>
              <p>{report.file?.filename ?? file?.name}</p>
            </div>
            <strong className="rc-rate">{percent(report.summary?.definite_resolution_rate)}<small>تعیین‌تکلیف قطعی</small></strong>
          </header>

          <div className="rc-kpis">
            <article className="green"><span>سندخورده</span><strong>{toFa(counts.posted)}</strong></article>
            <article className="amber"><span>نیازمند بررسی</span><strong>{toFa(counts.needs_review)}</strong></article>
            <article className="red"><span>بدون سند</span><strong>{toFa(counts.unposted)}</strong></article>
            <article className="blue"><span>انتقال داخلی</span><strong>{toFa(counts.internal_transfer)}</strong></article>
          </div>

          <div className="rc-result-actions">
            <a className="rc-primary" href={`/__reconciliation_proxy/reconciliation/${report.reconciliation_id}/export.xlsx`}>
              دانلود فایل خروجی Excel
            </a>
            <button className="rc-secondary" onClick={reset}>مغایرت‌گیری فایل جدید</button>
          </div>
          {balanceStatus(report) && (
            <p className="rc-human-note">{balanceStatus(report)}</p>
          )}
          <p className="rc-human-note">
            وضعیت «نیازمند بررسی» فقط کاندید بررسی انسانی است و به معنی مغایرت قطعی نیست.
          </p>
        </section>
      )}

      <footer className="rc-footer">
        <span>Finance Command Center</span>
        <small>این حساب فقط به پنل مغایرت‌گیری دسترسی دارد.</small>
      </footer>
    </main>
  );
}

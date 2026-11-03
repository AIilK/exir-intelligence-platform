"""خواندن و پاک‌سازی فایل Excel گزارش فروش.

فایل اصلی فقط خوانده می‌شود و هرگز تغییر نمی‌کند. خروجی یک دیکشنری از
DataFrameهای نرمال‌شده است که در data/cache ذخیره می‌شود تا بارگذاری بعدی سریع باشد.
"""
from __future__ import annotations

import hashlib
import pickle
import re
from pathlib import Path

import pandas as pd

CACHE_VERSION = 8
EXCEL_EXT = {".xlsb", ".xlsx", ".xlsm"}

# نگاشت ستون‌های خروجی سیستم فروش به نام‌های داخلی
COLMAP = {
    "تاریخ": "date",
    "نام شعبه": "branch",
    "کد سرپرست": "supervisor_code",
    "نام سرپرست": "supervisor",
    "کد فروشنده": "seller_code",
    "نام فروشنده": "seller",
    "کد کالا": "product_code",
    "نام کالا": "product",
    "cate": "category",
    "Brand": "brand_raw",
    "نام برند": "brand",
    "نام گروه کالا": "product_group",
    "نام شهر": "city",
    "نام مسیر": "route",
    "نام لاین": "line",
    "نحوه پرداخت": "payment",
    "نوع فاکتور": "inv_type",
    "شماره": "inv_no",
    "شناسه فاکتور": "inv_id",
    "شماره مرجع": "ref_no",
    "کد شعبه": "branch_code",
    "کد مشتری": "customer_code",
    "نام مشتری": "customer",
    "مجموع تعداد": "qty",
    "فی فروش": "unit_price",
    "جمع قبل تخفیف": "gross",
    "تخفیف حجمی": "vol_disc",
    "تخفیف نقدی": "cash_disc",
    "تخفیف مدیریتی": "mgmt_disc",
    "مجموع تخفیفات": "disc",
    "ارزش افزوده": "vat",
    "قابل پرداخت": "payable",
    "وضعیت درخواست": "status",
}
NUMERIC = ["qty", "unit_price", "gross", "vol_disc", "cash_disc", "mgmt_disc", "disc", "vat", "payable"]
# نام‌های جایگزین احتمالی ستون‌ها در خروجی‌های بعدی (به نام استاندارد COLMAP نگاشت می‌شوند)
ALIASES = {
    "تخفیف پروموشن": "تخفیف حجمی",
    "تخفیف پروموشن ماهانه": "تخفیف حجمی",
    "پروموشن ماهانه": "تخفیف حجمی",
    "تخفیف مدیریت": "تخفیف مدیریتی",
}
# ستون‌های مبلغی/تعدادی که در سطرهای برگشتی باید منفی باشند
SIGNED = ["qty", "gross", "vol_disc", "cash_disc", "mgmt_disc", "disc", "vat", "payable"]
TEXT = ["branch", "supervisor", "seller", "product", "category", "brand", "brand_raw",
        "product_group", "city", "route", "line", "payment", "inv_type", "customer"]
CODES = ["supervisor_code", "seller_code", "product_code", "customer_code", "branch_code"]
REQUIRED = ["date", "branch", "seller_code", "product_code", "customer_code", "qty", "gross"]
UNKNOWN = "نامشخص"
DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")


class DataError(Exception):
    pass


def _clean_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return UNKNOWN
    s = re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip()
    # خطاهای اکسل (#N/A و ...) در xlsb به صورت 0x2a یا 0 خوانده می‌شوند
    if s in ("", "0", "0x2a", "0x7", "0xf", "0x17", "0x1d", "0x24", "#N/A", "nan"):
        return UNKNOWN
    return s


def _clean_code(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=lambda c: re.sub(r"\s+", " ", str(c)).strip())
    df = df.rename(columns=lambda c: ALIASES.get(c, c))
    df = df.rename(columns=COLMAP)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise DataError(f"ستون‌های ضروری یافت نشد: {missing}")
    keep = [c for c in COLMAP.values() if c in df.columns]
    df = df[keep].copy()
    if not ({"disc", "vol_disc", "cash_disc", "mgmt_disc"} & set(df.columns)):
        raise DataError("هیچ ستون تخفیفی (تخفیف حجمی / نقدی / مدیریتی / مجموع تخفیفات) یافت نشد.")
    present = set(df.columns)
    df = df[df["product_code"].notna()]
    for c in NUMERIC:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)
    for c in TEXT:
        if c in df.columns:
            df[c] = df[c].map(_clean_text)
    for c in CODES:
        if c in df.columns:
            df[c] = df[c].map(_clean_code)
    if "brand" not in df.columns or (df["brand"] == UNKNOWN).all():
        df["brand"] = df.get("brand_raw", UNKNOWN)
    df["date"] = df["date"].astype(str).str.strip()
    bad = ~df["date"].str.match(DATE_RE)
    if bad.any():
        df = df[~bad]
    # تخفیف مدیریتی: اگر ستون جدا ندارد، هر مقداری از «مجموع تخفیفات» که در حجمی + نقدی نیامده
    if "mgmt_disc" not in present and "disc" in present:
        rest = df["disc"] - df["vol_disc"] - df["cash_disc"]
        df["mgmt_disc"] = rest.where(rest.abs() > 1, 0.0)
    # مجموع تخفیفات = پروموشن (حجمی) + نقدی + مدیریتی
    df["disc"] = df["vol_disc"] + df["cash_disc"] + df["mgmt_disc"]
    # خالص فاکتور = جمع قبل از تخفیف − هر سه تخفیف (بدون ارزش افزوده)؛ مرجوعی‌ها منفی‌اند و کسر می‌شوند
    df["net"] = df["gross"] - df["disc"]
    # کد فروشنده در شعب مختلف تکراری است (مثلاً ۱۲۲ و ۷۰۷ در دو شعبه، دو نفر متفاوت)
    df["seller_key"] = (df["branch_code"] + "-" + df["seller_code"]) if "branch_code" in df else df["seller_code"]
    return df.reset_index(drop=True)


def _open(path: Path):
    engine = "pyxlsb" if path.suffix.lower() == ".xlsb" else "openpyxl"
    xl = pd.ExcelFile(path, engine=engine)
    return xl, engine


def _read_working_days(xl) -> tuple[float | None, float | None]:
    """«تعداد روز کاری X از Y» در بالای شیت‌های گزارشی."""
    for name in ("TotalReport", "Goods&Group", "Sales rep Ranking", "Trend2"):
        if name not in xl.sheet_names:
            continue
        head = xl.parse(name, header=None, nrows=3)
        for _, row in head.iterrows():
            vals = list(row.values)
            for i, v in enumerate(vals):
                if isinstance(v, str) and "روز کاری" in v:
                    nums = [x for x in vals[i + 1:] if isinstance(x, (int, float)) and not pd.isna(x)]
                    if len(nums) >= 2:
                        return float(nums[0]), float(nums[1])
    return None, None


def _read_core_categories(xl, known: set[str]) -> list[str]:
    """گروه‌های کالای ستون‌های سمت چپ TotalReport (رنگ مو، اکسیدان، ...)."""
    if "TotalReport" not in xl.sheet_names:
        return []
    head = xl.parse("TotalReport", header=None, nrows=6)
    best = []
    for _, row in head.iterrows():
        found = []
        for v in row.values:
            if isinstance(v, str):
                c = _clean_text(v)
                if c in known and c != UNKNOWN and c not in found:
                    found.append(c)
        if len(found) > len(best):
            best = found
    return best if len(best) >= 2 else []


def _classify(df: pd.DataFrame) -> str | None:
    cols = {str(c).strip() for c in df.columns}
    if not {"جمع قبل تخفیف", "کد مشتری", "تاریخ", "کد کالا"} <= cols:
        return None
    inv = df["نوع فاکتور"] if "نوع فاکتور" in df.columns else pd.Series(dtype=object)
    if inv.notna().mean() > 0.5:
        return "sales"
    st = next((df[c] for c in df.columns if str(c).strip() == "وضعیت درخواست"), None)
    if st is not None and st.notna().mean() > 0.5:
        return "requests"
    return None


def finish(sales: pd.DataFrame, requests: pd.DataFrame | None):
    """علامت مرجوعی‌ها و خالص درخواست؛ مشترک بین منبع Excel و SQL."""
    sales["inv_type"] = sales["inv_type"].replace(UNKNOWN, "فروش")
    sales["is_return"] = sales["inv_type"].str.contains("برگشت")
    # مرجوعی همیشه از فروش کم شود، حتی اگر سیستم آن را با علامت مثبت خروجی داده باشد
    ret = sales["is_return"]
    for c in SIGNED:
        sales.loc[ret, c] = -sales.loc[ret, c].abs()
    sales.loc[ret, "net"] = sales.loc[ret, "gross"] - sales.loc[ret, "disc"]
    if requests is not None:
        # خالص درخواست = جمع قبل از تخفیف − فقط پروموشن ماهانه (ستون «تخفیف حجمی»)؛
        # تخفیف نقدی و مدیریتی در مرحله فاکتور اعمال می‌شوند
        requests["net"] = requests["gross"] - requests["vol_disc"]
        requests["status"] = pd.to_numeric(requests.get("status"), errors="coerce").fillna(0).astype(int)


def parse_workbook(path: Path) -> dict:
    xl, _ = _open(path)
    try:
        return _parse(xl, path)
    finally:
        xl.close()  # آزاد کردن قفل فایل در ویندوز


def _parse(xl, path: Path) -> dict:
    sales = requests = customers = None
    # ابتدا نام‌های شناخته‌شده، سپس تشخیص خودکار بر اساس ستون‌ها
    preferred = [n for n in ("Sheet", "درخواست") if n in xl.sheet_names]
    others = [n for n in xl.sheet_names if n not in preferred]
    for name in preferred + others:
        if sales is not None and requests is not None:
            break
        try:
            head = xl.parse(name, nrows=1)
        except Exception:
            continue
        cols = {str(c).strip() for c in head.columns}
        if not {"جمع قبل تخفیف", "کد مشتری", "کد کالا"} <= cols:
            continue
        df = xl.parse(name)
        kind = _classify(df)
        if kind == "sales" and sales is None:
            sales = _normalize(df); sales.attrs["sheet"] = name
        elif kind == "requests" and requests is None:
            requests = _normalize(df); requests.attrs["sheet"] = name
    if sales is None:
        raise DataError("شیت تراکنش‌های فروش (دارای ستون «نوع فاکتور») در فایل پیدا نشد.")
    finish(sales, requests)

    if "لیست مشتریان" in xl.sheet_names:
        c = xl.parse("لیست مشتریان")
        c = c.rename(columns=lambda x: str(x).strip())
        cols = {"شعبه": "branch", "کد": "customer_code", "نام کامل": "customer", "شهر": "city",
                "صنف": "trade", "گرید": "grade", "امتیاز RFM": "rfm", "اعتبار": "credit",
                "وضعیت مشتری": "active", "نحوه پرداخت": "payment"}
        c = c[[k for k in cols if k in c.columns]].rename(columns=cols)
        if "customer_code" in c.columns:
            c["customer_code"] = c["customer_code"].map(_clean_code)
            for k in ("branch", "customer", "city", "trade", "payment"):
                if k in c.columns:
                    c[k] = c[k].map(_clean_text)
            customers = c

    wd_elapsed, wd_total = _read_working_days(xl)
    core = _read_core_categories(xl, set(sales["category"]))
    if not core:  # در نبود سرستون در فایل: شش گروه پرفروش
        core = sales.groupby("category")["net"].sum().sort_values(ascending=False).head(6).index.tolist()
    return {
        "sales": sales,
        "requests": requests,
        "customers": customers,
        "meta": {
            "file": str(path),
            "file_name": path.name,
            "sheets": xl.sheet_names,
            "sales_sheet": sales.attrs.get("sheet"),
            "requests_sheet": requests.attrs.get("sheet") if requests is not None else None,
            "wd_elapsed_file": wd_elapsed,
            "wd_total_file": wd_total,
            "core_categories": core,
            "rows_sales": int(len(sales)),
            "rows_requests": int(len(requests)) if requests is not None else 0,
            "rows_customers": int(len(customers)) if customers is not None else 0,
        },
    }


def load(path: Path, cache_dir: Path) -> dict:
    st = path.stat()
    key = hashlib.sha1(f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{CACHE_VERSION}".encode()).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{key}.pkl"
    if cf.exists():
        try:
            with cf.open("rb") as f:
                return pickle.load(f)
        except Exception:
            cf.unlink(missing_ok=True)
    data = parse_workbook(path)
    with cf.open("wb") as f:
        pickle.dump(data, f)
    return data

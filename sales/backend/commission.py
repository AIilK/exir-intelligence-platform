"""درصد تحقق و پورسانت ویزیتورها و سرپرستان هیبرید (دستورالعمل‌های آبان ۱۴۰۵).

دو نوع ویزیتور:
  پورسانتی  : نرخ پلکانی بر اساس حجم فروش خالص ماه (هر استان گروه A جدول خودش، بقیه هیبریدها جدول گروه B)؛
              نرخ سطحِ تحقق‌یافته روی کل فروش اعمال می‌شود؛ ۱۵٪ پورسانت ذخیره کسر و هر ۶ ماه تسویه می‌شود.
  استخدامی  : پورسانت پایه از درصد تحقق تارگت ریالی (۲ / ۲.۵ / ۳٪) + پورسانت تکمیلی هر گروه کالا که دست‌کم ۸۰٪
              تارگت تعدادی آن محقق شده (حداکثر ۲٪)؛ سقف نرخ ۵٪ (با رزتی ۵.۲٪). فروش خالص زیر ۷۰۰ میلیون تومان = صفر.
فاکتورهای عمده (فروش خالص یک فاکتور بیش از ۷۰۰ میلیون تومان) فقط نرخ طبقه اول می‌گیرند (پورسانتی ۳٪، استخدامی ۲٪).
سرپرست: پلکانی (هر بخش با نرخ خودش) روی فروش خالص ویزیتورهای تیمش؛ زیر تارگت اول صفر؛ ۱۵٪ ذخیره.

مبنا: فروش خالص (پس از کسر برگشتی و تخفیفات، بدون ارزش افزوده). شرط وصول، مانده ۶۵٪ و ۲۰٪ عمده/مانده
در داده کارآمد نیستند و اعمال نمی‌شوند. همه مبالغ داخلی به ریال است.
فهرست ویزیتورها و تارگت‌ها هر ماه در data/commission ذخیره می‌شوند؛ هیچ چیز در دیتابیس کارآمد نوشته نمی‌شود.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

M = 1e6  # جدول‌های دستورالعمل به میلیون ریال‌اند

# ---------------------------------------------------------------- قواعد
# visitor: [حد بالای سطح (میلیون ریال، None = بیشتر)، نرخ]؛ supervisor: تارگت اول و دوم (میلیون ریال) و نرخ سه بخش
SUP_RATES = [0.0075, 0.01, 0.015]
RULESETS = {
    "هیبرید تهران": {"visitor": [[7000, .03], [15000, .05], [25000, .06], [40000, .07], [None, .09]],
                     "supervisor": {"t1": 120000, "t2": 250000}},
    "هیبرید آذربایجان غربی": {"visitor": [[7000, .03], [15000, .05], [25000, .06], [40000, .07], [None, .09]],
                              "supervisor": {"t1": 100000, "t2": 150000}},
    "هیبرید اصفهان": {"visitor": [[7000, .03], [15000, .05], [25000, .06], [40000, .07], [None, .09]],
                      "supervisor": {"t1": 100000, "t2": 200000}},
    "هیبرید کرمان": {"visitor": [[7000, .03], [15000, .05], [25000, .06], [40000, .07], [None, .09]],
                     "supervisor": {"t1": 100000, "t2": 150000}},
    # جدول خراسان سطح دوم را از ۲۰٬۰۰۰ نوشته (فاصله ۱۰ تا ۲۰ هزار خالی است)؛ اینجا از ۱۰٬۰۰۰ گرفته شده
    "هیبرید خراسان": {"visitor": [[10000, .03], [40000, .05], [60000, .06], [80000, .07], [None, .09]],
                      "supervisor": {"t1": 200000, "t2": 400000}},
    # دستورالعمل کرج بخش سرپرست ندارد
    "هیبرید البرز": {"visitor": [[10000, .03], [30000, .05], [40000, .06], [50000, .07], [None, .09]],
                     "supervisor": None},
    "B": {"visitor": [[7000, .03], [15000, .05], [25000, .06], [35000, .07], [None, .09]],
          "supervisor": {"t1": 20000, "t2": 40000}},
}
RULESET_LABEL = {"B": "گروه B (بقیه هیبریدها)"}

EMPLOYED = {
    "floor": 7000 * M,                               # فروش خالص کمتر از ۷۰۰ میلیون تومان: بدون پورسانت
    "base": [[0.70, .02], [0.95, .025], [None, .03]],  # [حد بالای تحقق ریالی، نرخ پایه]
    "group_min": 0.80,                               # حداقل تحقق تعدادی برای پورسانت تکمیلی هر گروه
    "group_cap": 0.02,
    "max_rate": 0.05,                                # سقف نرخ (پاداش رزتی جدا: تا ۵.۲٪)
    "wholesale_rate": 0.02,
}
COMMISSION = {"wholesale_rate": 0.03, "reserve": 0.15}
SUPERVISOR = {"reserve": 0.15}
WHOLESALE_INVOICE = 7000 * M                         # فاکتور عمده: مبلغ ناخالص یک فاکتور بیش از ۷۰۰ میلیون تومان

# گروه‌های تارگت تعدادی استخدامی‌ها. alt = کالای جایگزین برای فروشندگانی که مولهنس ندارند؛ extra = خارج از سقف ۲٪.
# هر گروه فقط برای ویزیتوری حساب می‌شود که برایش تارگت تعدادی ثبت شده است.
GROUPS = [
    {"key": "رنگ مو", "rate": .0025, "category": ["رنگ مو"]},
    {"key": "اکسیدان", "rate": .0025, "category": ["اکسیدان"]},
    {"key": "اسپری مو", "rate": .004, "category": ["اسپری مو"]},
    # تارگت و پورسانت عطر فقط برای ۳۵ میل است؛ ۲۷ میل گروه جدا و فقط برای نمایش (info: بدون تارگت و نرخ)
    {"key": "عطر ۳۵ میل", "rate": .0035, "category": ["عطر", "عطر مولهنس"], "product_like": "35"},
    {"key": "عطر ۲۷ میل", "rate": None, "category": ["عطر", "عطر مولهنس"], "product_like": "27", "info": True},
    {"key": "اسپری مولهنس", "rate": .004, "category": ["اسپری مولهنس"]},
    {"key": "پودر دکلره", "rate": .0035, "category": ["پودر دکلره"]},
    {"key": "لاک ناخن", "rate": .004, "category": ["لاک ناخن"], "alt": True},
    {"key": "آپ اسکای", "rate": .0035, "brand": ["آپ اسکای"], "alt": True},
    {"key": "بادی اسپلش پادینا", "rate": .0035, "category": ["بادی اسپلش"], "brand": ["پادینا"], "alt": True},
    {"key": "رولان لورینت", "rate": .004, "category": ["مام"], "brand": ["لورینت"], "product_like": "رول", "alt": True},
    {"key": "شامپو سیلور", "rate": .004, "category": ["شامپو سیلور"], "alt": True},
    {"key": "رزتی", "rate": .002, "brand": ["رزتی"], "extra": True},
]
GROUP_KEYS = [g["key"] for g in GROUPS if not g.get("info")]  # گروه‌هایی که تارگت می‌گیرند
TYPES = {"commission": "پورسانتی", "employed": "استخدامی"}


# ---------------------------------------------------------------- دستورالعمل هر ماه
# جدول‌های بالا (RULESETS، EMPLOYED، ...) دستورالعمل‌های آبان‌اند. هر ماه دستورالعمل خودش را دارد؛ ماهی که دستورالعمل
# جدا ندارد آخرین دستورالعمل پیش از خودش را می‌گیرد (ماه‌های پیش از اولین دستورالعمل، همان اولین را).
# «فاکتور ویژه»: فاکتورهایی که به‌جای نرخ سطح، نرخ ثابت پایه (wholesale_rate) می‌گیرند؛ special = نوع آن‌ها در آن ماه:
#   wholesale = فاکتور عمده (مبلغ ناخالص بیش از ۷۰۰ میلیون تومان)، mgmt = فاکتور دارای تخفیف مدیریتی.
# special_min: فاکتورهای ویژه هر نوع فقط وقتی جدا حساب می‌شوند که سهم آن نوع در فروش ناخالص همان فرد به حد برسد
#   (عمده: مبلغ عمده‌فروشی ÷ فروش ناخالص ≥ ۲۱٪؛ مدیریتی: تخفیف مدیریتی ÷ فروش ناخالص > ۱٪)؛ وگرنه همان فاکتورها
#   با نرخ عادی حساب می‌شوند (اعلام کاربر).
SPECIAL_MIN = {"wholesale": 0.21, "mgmt": 0.01}
# wholesale_rate = None: آن ماه فاکتور ویژه ندارد (فاکتور عمده و تخفیف مدیریتی فقط نمایش داده می‌شوند).
TIERS_A_1405_07 = [[7000, .03], [15000, .05], [25000, .06], [40000, .07], [None, .09]]
TIERS_B_1405_07 = [[5000, .03], [10000, .05], [30000, .07], [None, .09]]
SUP_B_1405_07 = {"t1": 40000, "t2": 50000}
RULES = {
    # «مهر - پورسانتی» و «مهر - استخدامی»؛ البرز و مازندران گروه B (اعلام کاربر)؛ ذخیره استخدامی ۱۰٪ (اعلام کاربر)
    "1405/07": {
        "title": "دستورالعمل‌های مهر ۱۴۰۵",
        "rulesets": {
            "هیبرید تهران": {"visitor": TIERS_A_1405_07, "supervisor": {"t1": 200000, "t2": 400000}},
            "A": {"visitor": TIERS_A_1405_07, "supervisor": {"t1": 100000, "t2": 150000}},
            "B": {"visitor": TIERS_B_1405_07, "supervisor": SUP_B_1405_07},
            # آذربایجان شرقی فقط در مهر: فروش ناخالص زیر ۷۰۰ میلیون تومان ۵٪، بالای آن ۷٪ (اعلام کاربر)؛ سرپرست مثل گروه B
            "هیبرید آذربایجان شرقی": {"visitor": [[7000, .05], [None, .07]], "supervisor": SUP_B_1405_07, "group": "B"},
        },
        "group_of": {b: "A" for b in ("هیبرید خراسان", "هیبرید کرمان", "هیبرید اصفهان", "هیبرید آذربایجان غربی")},
        "labels": {"هیبرید تهران": "هیبرید تهران (گروه A)", "A": "گروه A (خراسان، کرمان، اصفهان، آذربایجان غربی)",
                   "B": "گروه B (بقیه هیبریدها)", "هیبرید آذربایجان شرقی": "هیبرید آذربایجان شرقی (گروه B، جدول جدا)"},
        "sup_rates": SUP_RATES,
        # فاکتورهای عمده و فاکتورهای با تخفیف مدیریتی: پورسانتی ۳٪ (نرخ سطح اول)، استخدامی ۲٪ ثابت (اعلام کاربر، فقط مهر)
        "special": ["wholesale", "mgmt"], "special_min": SPECIAL_MIN,
        # مبنای پورسانت (ویزیتور، سرپرست و کف استخدامی): فروش خالص + تخفیف نقدی (اعلام کاربر، فقط مهر)
        "comm_base": "net_cash",
        "employed": {**EMPLOYED, "wholesale_rate": 0.02, "reserve": 0.10},
        "commission": {"wholesale_rate": 0.03, "reserve": 0.15},
        "supervisor": {"reserve": 0.15},
    },
    "1405/08": {
        "title": "دستورالعمل‌های آبان ۱۴۰۵",
        "rulesets": RULESETS, "group_of": {}, "labels": RULESET_LABEL, "sup_rates": SUP_RATES, "special": ["wholesale"],
        "special_min": SPECIAL_MIN,
        "employed": {**EMPLOYED, "reserve": 0.0}, "commission": COMMISSION, "supervisor": SUPERVISOR,
    },
}


def rules_for(month: str) -> dict:
    keys = sorted(RULES)
    past = [k for k in keys if k <= month]
    return RULES[past[-1] if past else keys[0]]


def rules_payload(month: str) -> dict:
    R = rules_for(month)
    return {**{k: R[k] for k in ("title", "rulesets", "labels", "sup_rates", "special", "employed", "commission", "supervisor")},
            "comm_base": R.get("comm_base") or "net", "special_min": R.get("special_min") or {},
            "wholesale_invoice": WHOLESALE_INVOICE, "groups": GROUPS}


# ---------------------------------------------------------------- روز کاری
def _j2g(jy: int, jm: int, jd: int):
    """تاریخ شمسی به میلادی (الگوریتم استاندارد jalaali)."""
    from datetime import date
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186)
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    ml = [0, 31, 29 if (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > ml[gm]:
        gd -= ml[gm]
        gm += 1
    return date(gy, gm, gd)


def _month_len(jy: int, jm: int) -> int:
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if (_j2g(jy + 1, 1, 1) - _j2g(jy, 12, 1)).days == 30 else 29


def workdays(month: str, today: str | None) -> tuple[int, int]:
    """(روز کاری سپری‌شده، کل روز کاری): همه روزهای ماه به‌جز جمعه؛ سپری‌شده = از اول ماه تا امروز (خود امروز هم)؛
    ماه گذشته = کل ماه."""
    jy, jm = int(month[:4]), int(month[5:7])
    n = _month_len(jy, jm)
    work = [d for d in range(1, n + 1) if _j2g(jy, jm, d).weekday() != 4]   # weekday ۴ = جمعه
    if today and today[:7] == month:
        return sum(1 for d in work if d <= int(today[8:10])), len(work)
    if today and today[:7] < month:
        return 0, len(work)
    return len(work), len(work)


# ---------------------------------------------------------------- نرمال‌سازی نام‌ها
def norm(s) -> str:
    s = str(s or "").replace("ي", "ی").replace("ك", "ک").replace("\xa0", " ").replace("‌", " ")
    return re.sub(r"\s+", " ", s).strip()


def clean_name(s) -> str:
    """نام ویزیتور بدون شماره تلفن و جداکننده‌ها (فایل فهرست شماره همراه را کنار نام نوشته)."""
    s = norm(s).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    s = re.sub(r"[-/]?\s*0?9\d{9}", " ", s)
    s = re.sub(r"\d{6,}", " ", s)
    return re.sub(r"\s+", " ", s.replace("/", " ").replace("\t", " ")).strip(" -/")


def phone_of(s) -> str:
    """شماره همراه داخل یک متن (نام یا ستون موبایل)، به شکل یکسان ۱۱ رقمی 09xxxxxxxxx؛ نبود = ''."""
    t = norm(s).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    m = re.search(r"(?<!\d)0?(9\d{9})(?!\d)", t)
    return f"0{m.group(1)}" if m else ""


def bkey(branch) -> str:
    """کلید مقایسه نام شعبه («هیبریدی مازندران» در کارآمد = «هیبرید مازندران» در فهرست)."""
    return re.sub(r"^هیبریدی(?= )", "هیبرید", norm(branch))


def ruleset_of(branch: str, R: dict) -> str:
    b = bkey(branch)
    return R["group_of"].get(b) or (b if b in R["rulesets"] else "B")


def group_ab(rs: str, R: dict) -> str:
    """گروه A/B برای فیلتر: جدول جدای یک شعبه گروهش را با "group" می‌گوید."""
    return R["rulesets"].get(rs, {}).get("group") or ("B" if rs == "B" else "A")


def visitor_rate(volume: float, tiers: list) -> tuple[int, float]:
    """(شماره سطح از ۱، نرخ) برای فروش خالص volume (ریال)."""
    for i, (upper, rate) in enumerate(tiers):
        if upper is None or volume < upper * M:
            return i + 1, rate
    return len(tiers), tiers[-1][1]


def supervisor_commission(sales: float, rule: dict | None, rates: list = SUP_RATES, reach: float | None = None) -> float | None:
    """پلکانی روی sales (فروش خالص تیم): تا تارگت اول ۰.۷۵٪، تا تارگت دوم ۱٪، مازاد ۱.۵٪.
    رسیدن به تارگت اول با reach (فروش ناخالص تیم، اعلام کاربر) سنجیده می‌شود؛ نرسیده = صفر."""
    if not rule:
        return None
    t1, t2 = rule["t1"] * M, rule["t2"] * M
    if (sales if reach is None else reach) < t1:
        return 0.0
    r1, r2, r3 = rates
    # هر پله فقط بخشی از فروش خالص که داخل همان پله است (فروش خالص ممکن است زیر تارگتی باشد که ناخالص به آن رسیده)
    s = max(sales, 0.0)
    return min(s, t1) * r1 + max(min(s, t2) - t1, 0) * r2 + max(s - t2, 0) * r3


# ---------------------------------------------------------------- فهرست ویزیتورها (اکسل)
def _cell_blue(cell) -> str | None:
    """رنگ هاشور خانه نام: آبی = پورسانتی؛ قرمز هم برگردانده می‌شود تا در یادداشت بیاید."""
    f = cell.fill
    if not f or not f.fill_type or f.fill_type in ("none", "solid"):
        return None
    bg = f.bgColor
    if bg is not None and bg.type == "rgb" and str(bg.rgb).upper().endswith("FF0000"):
        return "red"
    if bg is not None and bg.type == "theme" and bg.theme in (4, 8):
        return "blue"
    return "other"


def import_roster(data: bytes) -> dict:
    """فایل «لیست ویزیتور و سرپرست»: برگه اول شعبه/سرپرست/کد/نام (خانه نام با هاشور آبی = پورسانتی)،
    برگه دوم فهرست سرپرستان."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.worksheets[0]
    hdr_row, cols = None, {}
    for r in range(1, min(ws.max_row, 15) + 1):
        vals = [norm(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)]
        if "کد فروشنده" in vals and "نام فروشنده" in vals:
            hdr_row = r
            cols = {v: i + 1 for i, v in enumerate(vals) if v}
            break
    if hdr_row is None:
        raise ValueError("ستون‌های «کد فروشنده» و «نام فروشنده» در برگه اول پیدا نشد.")
    cb, cs, cc, cn = cols.get("نام شعبه"), cols.get("نام سرپرست"), cols["کد فروشنده"], cols["نام فروشنده"]
    note_col = max(cols.values()) + 1
    visitors, branch, sup = [], "", ""
    for r in range(hdr_row + 1, ws.max_row + 1):
        name_cell = ws.cell(r, cn)
        name = clean_name(name_cell.value)
        # سطر بدون نام شعبه ادامه سطر قبل است (شعبه و سرپرست را از بالا می‌گیرد)
        if cb and ws.cell(r, cb).value:
            branch = norm(ws.cell(r, cb).value)
            sup = clean_name(ws.cell(r, cs).value) if cs else ""
        if not name:
            continue
        code = ws.cell(r, cc).value
        code = str(int(code)) if isinstance(code, (int, float)) else norm(code)
        color = _cell_blue(name_cell)
        notes = [norm(ws.cell(r, c).value) for c in range(note_col, ws.max_column + 1) if ws.cell(r, c).value]
        if color == "red":
            notes.append("رنگ قرمز در فایل فهرست")
        phone = phone_of(name_cell.value)
        visitors.append({"id": f"{branch}|{code or name}", "branch": branch, "supervisor": sup, "code": code,
                         "name": name, "phone": phone, "phone_from": "فایل لیست" if phone else "",
                         "type": "commission" if color == "blue" else "employed",
                         "note": "، ".join(n for n in notes if n)})
    sups = []
    if len(wb.worksheets) > 1:
        s2 = wb.worksheets[1]
        for r in range(2, s2.max_row + 1):
            b, n = norm(s2.cell(r, 1).value), clean_name(s2.cell(r, 2).value)
            if b and n:
                sups.append({"branch": b, "name": n})
    # ویزیتور بدون سرپرست: اگر برگه سرپرستان برای آن شعبه فقط یک نفر دارد
    by_branch: dict[str, list] = {}
    for s in sups:
        by_branch.setdefault(bkey(s["branch"]), []).append(s["name"])
    for v in visitors:
        names = by_branch.get(bkey(v["branch"]), [])
        if not v["supervisor"] and len(names) == 1:
            v["supervisor"] = names[0]
    # شناسه تکراری (یک کد دو بار در یک شعبه) یکتا شود
    seen = {}
    for v in visitors:
        k = v["id"]
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:
            v["id"] = f"{k}#{seen[k]}"
    return {"visitors": visitors, "supervisors": sups}


# سرستون‌های فایل‌های تارگت استان‌ها ← گروه تارگت تعدادی. سرستونی که اینجا نیست خوانده نمی‌شود و گزارش می‌شود.
HEADER_GROUPS = {
    "رنگ مو": "رنگ مو", "اکسیدان": "اکسیدان", "اسپری مو": "اسپری مو", "عطر": "عطر ۳۵ میل", "عطر مولهنس": "عطر ۳۵ میل",
    "اسپری مولهنس": "اسپری مولهنس", "مولهنس": "اسپری مولهنس",  # فایل یزد (تأیید کاربر)
    "پودر دکلره": "پودر دکلره", "لاک ناخن": "لاک ناخن", "آپ اسکای": "آپ اسکای",
    "محصولات آپسکای": "آپ اسکای", "بادی اسپلش پادینا": "بادی اسپلش پادینا", "رولان لورینت": "رولان لورینت",
    "شامپو سیلور": "شامپو سیلور", "rozetti": "رزتی", "rozzetti": "رزتی", "رزتی": "رزتی",
}


def _hkey(v) -> str:
    return norm(v).lower()


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", norm(s))


def _match_name(name: str, branch: str, visitors: list[dict]) -> str | None:
    """نام فایل تارگت (گاهی فقط نام خانوادگی، گاهی با فاصله یا نیم‌فاصله متفاوت) ← شناسه ویزیتور همان شعبه؛
    فقط وقتی دقیقاً یک ویزیتور همه کلمه‌های نام را داشته باشد."""
    words = clean_name(name).split()
    if not words:
        return None
    cand = [v for v in visitors if bkey(v["branch"]) == bkey(branch)
            and all(w in _squash(clean_name(v["name"])) for w in words)]
    return cand[0]["id"] if len(cand) == 1 else None


def import_targets(data: bytes, visitors: list[dict], branch: str | None = None) -> dict:
    """فایل تارگت ویزیتورها. سطر سرستون سطری است که خانه «ویزیتور» (یا «نام ویزیتور») دارد:
    «تارگت ریالی» (به ریال) و یک ستون تعدادی برای هر گروه کالا. شعبه = پارامتر branch (هر فایل مال یک شعبه).
    سطرهای «جمع» و سطرهای بدون نام خوانده نمی‌شوند."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out, missing, unmapped, rial_heads = {}, [], set(), set()
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        hi = next((i for i, r in enumerate(rows[:10]) if any(norm(v) in ("ویزیتور", "نام ویزیتور") for v in r)), None)
        if hi is None:
            continue
        head = {j: _hkey(v) for j, v in enumerate(rows[hi]) if v is not None}
        c_name = next(j for j, t in head.items() if t in ("ویزیتور", "نام ویزیتور"))
        c_rial = next((j for j, t in head.items() if t.startswith("تارگت ریالی")), None)
        if c_rial is not None:
            rial_heads.add(norm(rows[hi][c_rial] if c_rial < len(rows[hi]) and rows[hi][c_rial] else head[c_rial]))
        c_groups = {}
        for j, t in head.items():
            if j in (c_name, c_rial):
                continue
            g = HEADER_GROUPS.get(re.sub(r"\s+", " ", t))
            if g:
                c_groups[j] = g
            else:
                unmapped.add(norm(rows[hi][j]) if j < len(rows[hi]) and rows[hi][j] else t)
        cell = lambda r, j: r[j] if j is not None and j < len(r) else None
        for r in rows[hi + 1:]:
            name = clean_name(cell(r, c_name))
            if not name or name.startswith("جمع") or name.lower() in ("sum", "total"):
                continue
            b = branch or ""
            rial = cell(r, c_rial)
            vid = _match_name(name, b, visitors) if b else None
            t = {"groups": {g: float(cell(r, j)) for j, g in c_groups.items() if isinstance(cell(r, j), (int, float)) and cell(r, j) > 0}}
            if isinstance(rial, (int, float)) and rial > 0:
                t["rial"] = float(rial)
            if not vid:
                missing.append({"branch": b, "name": name, "rial": t.get("rial"), "groups": t["groups"]})
                continue
            out[vid] = t
    return {"targets": out, "missing": missing, "unmapped": sorted(unmapped), "rial_heads": sorted(rial_heads)}


def import_branch_targets(data: bytes) -> dict:
    """فایل «تارگت ناخالص» شعبه‌ها: سطر «نام شعبه»؛ بالای آن «تارگت تعدادی» و «تارگت ریالی» ستون‌ها را گروه‌بندی می‌کنند؛
    ستون «ناخالص» = تارگت ریالی کل شعبه."""
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hi = next((i for i, r in enumerate(rows[:10]) if any(norm(v) == "نام شعبه" for v in r)), None)
    if hi is None:
        raise ValueError("سطر «نام شعبه» در فایل پیدا نشد.")
    section, sec_of = None, {}
    top = rows[hi - 1] if hi > 0 else []
    for j in range(len(rows[hi])):
        t = norm(top[j]) if j < len(top) else ""
        if t.startswith("تارگت تعدادی"):
            section = "qty"
        elif t.startswith("تارگت ریالی"):
            section = "rial"
        sec_of[j] = section
    c_b = next(j for j, v in enumerate(rows[hi]) if norm(v) == "نام شعبه")
    out, unmapped = {}, set()
    for r in rows[hi + 1:]:
        b = norm(r[c_b]) if c_b < len(r) else ""
        if not b or b.lower() == "total" or b.startswith("جمع"):
            continue
        t = {"groups": {}, "groups_rial": {}}
        for j, h in enumerate(rows[hi]):
            if j == c_b or h is None or j >= len(r) or not isinstance(r[j], (int, float)):
                continue
            hk = re.sub(r"\s+", " ", _hkey(h))
            if hk == "ناخالص":
                t["rial"] = float(r[j])
                continue
            g = HEADER_GROUPS.get(hk)
            if not g:
                unmapped.add(norm(h))
                continue
            (t["groups"] if sec_of.get(j) == "qty" else t["groups_rial"])[g] = float(r[j])
        out[bkey(b)] = t
    return {"targets": out, "unmapped": sorted(unmapped)}


# ---------------------------------------------------------------- تکمیل از کارآمد
KARAMAD_VISITORS_SQL = """
SELECT BranchName, Code, Name, Mobile, Status FROM dbo.vwVisitor WHERE BranchName LIKE N'%هیبرید%'"""


def enrich_from_karamad(visitors: list[dict], kv: pd.DataFrame) -> list[dict]:
    """تلفن و کد ویزیتورها از جدول ویزیتور کارآمد (فقط خواندن). خروجی: فهرست تغییرها و ناهمخوانی‌ها برای نمایش.
      - تلفن: اگر در فایل لیست نیست، از ستون Mobile و اگر خالی بود از نام فروشنده در کارآمد.
      - ویزیتور بدون کد: فقط اگر در همان شعبه دقیقاً یک فروشنده کارآمد همه کلمه‌های نام را (به‌صورت کلمه کامل) داشته باشد.
      - نام کارآمد برای همان کد ذخیره می‌شود؛ اگر با نام فایل لیست نخواند، گزارش می‌شود (چیزی خودکار عوض نمی‌شود)."""
    kv = kv.assign(b=kv["BranchName"].map(bkey), c=kv["Code"].astype(str), n=kv["Name"].map(clean_name))
    log = []
    for v in visitors:
        b = bkey(v["branch"])
        row = None
        if v.get("code"):
            hit = kv[(kv["b"] == b) & (kv["c"] == str(v["code"]))]
            row = hit.iloc[0] if len(hit) else None
        else:
            words = clean_name(v["name"]).split()
            hit = kv[(kv["b"] == b) & kv["n"].map(lambda n: all(w in n.split() for w in words))]
            if len(hit) == 1:
                row = hit.iloc[0]
                v["code"] = row["c"]
                log.append({"id": v["id"], "name": v["name"], "kind": "code", "text": f"کد {row['c']} از کارآمد ({row['n']})"})
            elif len(hit) > 1:
                log.append({"id": v["id"], "name": v["name"], "kind": "ambiguous",
                            "text": "چند فروشنده هم‌نام در کارآمد: " + "، ".join(f"{n} ({c})" for n, c in zip(hit["n"], hit["c"]))})
        if row is None:
            if v.get("code") or not any(x["id"] == v["id"] for x in log):
                log.append({"id": v["id"], "name": v["name"], "kind": "notfound", "text": "در جدول ویزیتور کارآمد پیدا نشد"})
            continue
        v["karamad_name"] = row["n"]
        # نام کد در کارآمد با فایل لیست نمی‌خواند (کد به فرد دیگری داده شده): تلفن برداشته نمی‌شود
        if not set(clean_name(v["name"]).split()) & set(row["n"].split()):
            log.append({"id": v["id"], "name": v["name"], "kind": "mismatch",
                        "text": f"نام این کد در کارآمد «{row['n']}» است"})
            continue
        if not v.get("phone"):
            ph = phone_of(row["Mobile"]) or phone_of(row["Name"])
            if ph:
                v["phone"], v["phone_from"] = ph, "کارآمد"
                log.append({"id": v["id"], "name": v["name"], "kind": "phone", "text": f"تلفن {ph} از کارآمد"})
    return log


def rematch_missing(plan: dict) -> int:
    """ردیف‌های فایل تارگت که قبلاً به ویزیتوری وصل نشده بودند، با فهرست تازه دوباره وصل می‌شوند."""
    n = 0
    tm = plan.get("target_missing") if isinstance(plan.get("target_missing"), dict) else {}
    for b, lst in tm.items():
        keep = []
        for m in lst:
            vid = _match_name(m["name"], m["branch"], plan.get("visitors", []))
            if vid:
                plan.setdefault("targets", {})[vid] = {"groups": m.get("groups") or {}, **({"rial": m["rial"]} if m.get("rial") else {})}
                n += 1
            else:
                keep.append(m)
        tm[b] = keep
    plan["target_missing"] = tm
    return n


# ---------------------------------------------------------------- ذخیره ماهانه
class Store:
    """هر ماه یک فایل: فهرست ویزیتورها و سرپرستان (نوع هر ویزیتور) و تارگت‌ها. ماه تازه فهرست آخرین ماه قبل را می‌گیرد."""

    def __init__(self, folder: Path):
        self.folder = folder

    def _path(self, month: str) -> Path:
        return self.folder / f"{month.replace('/', '-')}.json"

    def months(self) -> list[str]:
        return sorted(p.stem.replace("-", "/") for p in self.folder.glob("1*.json")) if self.folder.is_dir() else []

    def get(self, month: str) -> dict:
        p = self._path(month)
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        prev = [m for m in self.months() if m < month]
        src = json.loads(self._path(prev[-1]).read_text(encoding="utf-8")) if prev else {}
        return {"month": month, "visitors": src.get("visitors", []), "supervisors": src.get("supervisors", []),
                "excluded_branches": src.get("excluded_branches", []),
                # حقوق ثابت ماهانه ثابت است: جدول ماه قبل به ماه تازه می‌آید
                **({"salaries": src["salaries"]} if src.get("salaries") else {}),
                "targets": {}, "saved": False, "roster_from": prev[-1] if prev else None}

    def put(self, plan: dict) -> dict:
        self.folder.mkdir(parents=True, exist_ok=True)
        plan = {**plan, "saved": True, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        plan.pop("roster_from", None)
        tmp = self._path(plan["month"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._path(plan["month"]))
        return plan


# ---------------------------------------------------------------- تطبیق با داده فروش
def match_sellers(visitors: list[dict], sales: pd.DataFrame) -> dict[str, dict]:
    """شناسه ویزیتور ← seller_key داده. اول با (شعبه، کد)؛ ویزیتورهای بدون کد با نام (فقط اگر یک فروشنده یکتا پیدا شود)."""
    s = sales.drop_duplicates("seller_key")[["seller_key", "seller", "seller_code", "branch"]].copy()
    s["b"] = s["branch"].map(bkey)
    s["n"] = s["seller"].map(clean_name)
    by_code = {(b, str(c)): k for b, c, k in zip(s["b"], s["seller_code"], s["seller_key"])}
    used = set()
    out = {}
    for v in visitors:
        b = bkey(v["branch"])
        k = by_code.get((b, str(v["code"]))) if v.get("code") else None
        if k:
            out[v["id"]] = {"key": k, "how": "code"}
            used.add(k)
    for v in visitors:
        if v["id"] in out or not v.get("name"):
            continue
        b, words = bkey(v["branch"]), clean_name(v["name"]).split()
        cand = s[(s["b"] == b) & ~s["seller_key"].isin(used)]
        cand = cand[cand["n"].map(lambda n: all(w in n for w in words))]
        if len(cand) == 1:
            k = cand["seller_key"].iloc[0]
            out[v["id"]] = {"key": k, "how": "name", "data_code": str(cand["seller_code"].iloc[0])}
            used.add(k)
    return out


def _group_mask(df: pd.DataFrame, g: dict) -> pd.Series:
    m = pd.Series(True, index=df.index)
    if g.get("category"):
        m &= df["category"].isin(g["category"])
    if g.get("brand"):
        m &= df["brand"].isin(g["brand"])
    if g.get("product_like"):
        m &= df["product"].astype(str).str.contains(g["product_like"], regex=False)
    return m


def _report_metrics(fs: pd.DataFrame, rq: pd.DataFrame | None, by: list[str]) -> pd.DataFrame:
    """ستون‌های شیت Report فایل «عملکرد و تحقق تارگت فروشنده» (فاکتور شامل برگشتی‌ها با علامت منفی):
    ریال خالص درخواست = قابل پرداخت − ارزش افزوده درخواست‌ها؛ ریال ناخالص فاکتور = جمع قبل تخفیف؛
    ریال خالص فاکتور = قابل پرداخت − ارزش افزوده؛ فروش تعدادی = مجموع تعداد؛
    مشتری = مشتریانی که جمع مجموع تعداد آن‌ها مثبت است."""
    g = fs.assign(xnet=fs["payable"] - fs["vat"]).groupby(by, observed=True).agg(
        gross=("gross", "sum"), xnet=("xnet", "sum"), qty=("qty", "sum"))
    cq = fs.groupby(by + ["customer_code"], observed=True)["qty"].sum()
    g["customers"] = cq[cq > 0].groupby(level=list(range(len(by)))).size()
    if rq is not None and len(rq):
        g = g.join(rq.assign(rnet=rq["payable"] - rq["vat"]).groupby(by, observed=True)["rnet"].sum().rename("req_net"), how="outer")
    else:
        g["req_net"] = 0.0
    return g.fillna(0)


def compute(plan: dict, sales: pd.DataFrame, requests: pd.DataFrame | None, month: str,
            wd_elapsed: float, wd_total: float, pace: float | None) -> dict:
    """sales / requests: همه سطرها (بدون ارزش افزوده)؛ pace = کل روز کاری ÷ روز کاری سپری‌شده (فقط ماه جاری).
    تحقق تارگت مثل فایل «عملکرد و تحقق تارگت فروشنده»:
      تارگت تا روز = تارگت ریالی ÷ کل روز کاری ماه × روز کاری سپری‌شده
      تحقق = ریال ناخالص فاکتور (جمع قبل تخفیف، برگشتی‌ها کسر) ÷ تارگت تا روز"""
    R = rules_for(month)
    # شعبه‌های حذف‌شده از پورسانت (excluded_branches) نه در ویزیتورها، نه در شعبه‌ها و نه در فروشندگان بی‌فهرست می‌آیند
    excl = {bkey(b) for b in plan.get("excluded_branches") or []}
    visitors = [v for v in plan.get("visitors", []) if bkey(v["branch"]) not in excl]
    targets = plan.get("targets", {})
    if excl:
        sales = sales[~sales["branch"].map(bkey).isin(excl)]
        requests = requests[~requests["branch"].map(bkey).isin(excl)] if requests is not None else None
    match = match_sellers(visitors, sales)
    ms = sales[sales["date"].str.startswith(month)]
    mr = requests[requests["date"].str.startswith(month)] if requests is not None else None
    keys = {m["key"] for m in match.values()}
    mine = ms[ms["seller_key"].isin(keys)]
    day_share = wd_elapsed / wd_total if wd_total else 1.0
    rep = _report_metrics(ms, mr, ["seller_key"])
    # فروش ناخالص و خالص از ابتدای سال همین ماه تا پایان همین ماه (برگشتی‌ها کسر؛ مثل ستون‌های «فروش ناخالص» و «فروش خالص»)
    ys = sales[(sales["date"] >= f"{month[:4]}/01/01") & (sales["date"].str[:7] <= month)]
    gross_ytd = ys.groupby("seller_key")["gross"].sum()
    net_ytd = ys.groupby("seller_key")["net"].sum()
    ms2 =ms.assign(group2=ms["category"].astype(str) + "-" + ms["brand"].astype(str))
    mr2 = mr.assign(group2=mr["category"].astype(str) + "-" + mr["brand"].astype(str)) if mr is not None else None
    rep_g = _report_metrics(ms2[ms2["seller_key"].isin(keys)], mr2[mr2["seller_key"].isin(keys)] if mr2 is not None else None,
                            ["seller_key", "group2"])

    agg = mine.groupby("seller_key").agg(net=("net", "sum"), qty=("qty", "sum"), cash=("cash_disc", "sum"))
    sales_only = mine[~mine["is_return"]]
    agg["sales_net"] = sales_only.groupby("seller_key")["net"].sum()
    agg["returns_net"] = -mine[mine["is_return"]].groupby("seller_key")["net"].sum()
    # فاکتور عمده: فاکتور فروشی که مبلغ ناخالصش (جمع قبل تخفیف) بیش از ۷۰۰ میلیون تومان است (اعلام کاربر).
    # wholesale = فروش خالص همان فاکتورها (برای نرخ جدا در ماه‌هایی که دستورالعمل قاعده‌اش را دارد)
    inv = sales_only.assign(mgmt=sales_only["mgmt_disc"] if "mgmt_disc" in sales_only else 0.0) \
        .groupby(["seller_key", "inv_id"]).agg(gross=("gross", "sum"), net=("net", "sum"), mgmt=("mgmt", "sum"), cash=("cash_disc", "sum"),
                                               inv_no=("inv_no", "first"), date=("date", "first"), customer=("customer", "first"))
    big = inv[inv["gross"] > WHOLESALE_INVOICE]
    agg["wholesale"] = big["net"].groupby(level=0).sum()
    agg["wholesale_gross"] = big["gross"].groupby(level=0).sum()
    agg["wholesale_n"] = big.groupby(level=0).size()
    # فاکتورهای فروش دارای تخفیف مدیریتی (از کارآمد: انواع تخفیف با نام «مدیریت»): تعداد، مبلغ ناخالص و مبلغ تخفیف
    md = inv[inv["mgmt"] > 0]
    agg["mgmt_n"] = md.groupby(level=0).size()
    agg["mgmt_inv_gross"] = md["gross"].groupby(level=0).sum()
    # خالص + تخفیف نقدی همان فاکتورها: مبنای پورسانت فاکتورهای ویژه (comm_base = net_cash)
    agg["mgmt_inv_net_cash"] = (md["net"] + md["cash"]).groupby(level=0).sum()
    agg["mgmt_disc"] = md["mgmt"].groupby(level=0).sum()
    agg["sales_gross"] = sales_only.groupby("seller_key")["gross"].sum()
    # فاکتورهای ویژه همین ماه (عمده و/یا با تخفیف مدیریتی، طبق R["special"]): نرخ ثابت پایه به‌جای نرخ سطح
    kinds = R.get("special") or []
    is_ws, is_mg = inv["gross"] > WHOLESALE_INVOICE, inv["mgmt"] > 0
    # حد سهم هر نوع (special_min) با فروش ناخالص همان فرد (ستون «فروش ناخالص»، برگشتی‌ها کسر):
    # درصد عمده‌فروشی = مبلغ ناخالص فاکتورهای عمده ÷ فروش ناخالص؛ درصد فروش مدیریتی = تخفیف مدیریتی ÷ فروش ناخالص
    smin = R.get("special_min") or {}
    g_k = rep["gross"].reindex(agg.index).fillna(0)
    ws_share = (agg["wholesale_gross"].fillna(0) / g_k).where(g_k > 0)
    mg_share = (agg["mgmt_disc"].fillna(0) / g_k).where(g_k > 0)
    ws_on = set(agg.index[ws_share >= smin["wholesale"]]) if "wholesale" in smin else set(agg.index)
    mg_on = set(agg.index[mg_share > smin["mgmt"]]) if "mgmt" in smin else set(agg.index)
    seller = inv.index.get_level_values(0)
    sp = inv[(is_ws & ("wholesale" in kinds) & seller.isin(ws_on)) | (is_mg & ("mgmt" in kinds) & seller.isin(mg_on))]
    # تفکیک برند فاکتورهای عمده هر فرد (از سطرهای همان فاکتورها)
    wl = sales_only.set_index(["seller_key", "inv_id"])
    wl = wl[wl.index.isin(big.index)].reset_index()
    wb = wl.assign(nc=wl["net"] + wl["cash_disc"]).groupby(["seller_key", "brand"], observed=True)[["gross", "net", "nc"]].sum()
    ws_brands = {k: [{"brand": str(b), "gross": float(r.gross), "net": float(r.net), "net_cash": float(r.nc)}
                     for b, r in g.droplevel(0).sort_values("gross", ascending=False).iterrows()]
                 for k, g in wb.groupby(level=0)}
    agg["special_net"] = sp["net"].groupby(level=0).sum()
    agg["special_net_cash"] = (sp["net"] + sp["cash"]).groupby(level=0).sum()
    agg["special_gross"] = sp["gross"].groupby(level=0).sum()
    agg["special_n"] = sp.groupby(level=0).size()
    sp_list = {k: [{"inv_no": str(r.inv_no), "date": str(r.date), "customer": str(r.customer), "gross": float(r.gross),
                    "net": float(r.net), "net_cash": float(r.net + r.cash), "mgmt": float(r.mgmt), "wholesale": bool(r.gross > WHOLESALE_INVOICE),
                    "mgmt_inv": bool(r.mgmt > 0)} for r in g.sort_values("date").itertuples()]
               for k, g in sp.reset_index(level=1, drop=True).groupby(level=0)}
    agg = agg.fillna(0)
    gq = {g["key"]: mine[_group_mask(mine, g)].groupby("seller_key")["qty"].sum() for g in GROUPS}
    gn = {g["key"]: mine[_group_mask(mine, g)].groupby("seller_key")["net"].sum() for g in GROUPS}

    rows = []
    for v in visitors:
        mt = match.get(v["id"])
        k = mt["key"] if mt else None
        a = agg.loc[k] if k in agg.index else None
        net = float(a["net"]) if a is not None else 0.0
        wholesale = float(a["wholesale"]) if a is not None else 0.0
        t = targets.get(v["id"]) or {}
        t_rial = t.get("rial") or None
        tg = {g: q for g, q in (t.get("groups") or {}).items() if q}
        groups = []
        for g in GROUPS:
            act = float(gq[g["key"]].get(k, 0)) if k else 0.0
            tq = tg.get(g["key"])
            groups.append({"key": g["key"], "qty": act, "net": float(gn[g["key"]].get(k, 0)) if k else 0.0,
                           "target": tq, "ach": act / tq if tq else None,
                           "target_day": tq * day_share if tq else None, "ach_day": act / (tq * day_share) if tq and day_share else None})
        rp = rep.loc[k] if k in rep.index else None
        gross = float(rp["gross"]) if rp is not None else 0.0
        t_day = t_rial * day_share if t_rial else None
        g2 = []
        if k is not None and k in rep_g.index.get_level_values(0):
            gg = rep_g.loc[k].sort_values("gross", ascending=False)
            g2 = [{"group": i, **{c: float(gg.at[i, c]) for c in ("req_net", "gross", "xnet", "qty", "customers")}} for i in gg.index]
        row = {"id": v["id"], "branch": v["branch"], "supervisor": v.get("supervisor") or "", "code": v.get("code") or "",
               "name": v["name"], "phone": v.get("phone") or "", "phone_from": v.get("phone_from") or "",
               "karamad_name": v.get("karamad_name") or "",
               "type": v["type"], "type_label": TYPES[v["type"]], "note": v.get("note") or "",
               "ruleset": ruleset_of(v["branch"], R), "seller_key": k, "match": mt["how"] if mt else None,
               "net": net, "sales_net": float(a["sales_net"]) if a is not None else 0.0,
               "returns_net": float(a["returns_net"]) if a is not None else 0.0,
               "wholesale": wholesale, "wholesale_n": int(a["wholesale_n"]) if a is not None else 0,
               "forecast": net * pace if pace else net, "gross_forecast": gross * pace if pace else gross,
               "target_rial": t_rial,
               "req_net": float(rp["req_net"]) if rp is not None else 0.0, "gross": gross,
               "xnet": float(rp["xnet"]) if rp is not None else 0.0, "qty": float(rp["qty"]) if rp is not None else 0.0,
               "customers": int(rp["customers"]) if rp is not None else 0,
               "target_day": t_day, "ach": gross / t_day if t_day else None, "groups": groups, "groups2": g2,
               "gross_ytd": float(gross_ytd.get(k, 0.0)) if k else 0.0,
               "net_ytd": float(net_ytd.get(k, 0.0)) if k else 0.0}
        mgmt = float(a["mgmt_disc"]) if a is not None else 0.0
        mgmt_inv = float(a["mgmt_inv_gross"]) if a is not None else 0.0
        sales_gross = float(a["sales_gross"]) if a is not None else 0.0
        row.update(special_net=float(a["special_net"]) if a is not None else 0.0,
                   special_gross=float(a["special_gross"]) if a is not None else 0.0,
                   special_n=int(a["special_n"]) if a is not None else 0, special_invoices=sp_list.get(k, []),
                   wholesale_brands=ws_brands.get(k, []),
                   special_ws_on=("wholesale" in kinds) and k in ws_on, special_mg_on=("mgmt" in kinds) and k in mg_on)
        # مبنای پورسانت ماه: فروش خالص، یا فروش خالص + تخفیف نقدی (comm_base = net_cash)
        net_cash = net + (float(a["cash"]) if a is not None else 0.0)
        use_cash = R.get("comm_base") == "net_cash"
        base = net_cash if use_cash else net
        row.update(net_cash=net_cash, base=base, base_forecast=base * pace if pace else base,
                   special_base=(float(a["special_net_cash"]) if a is not None else 0.0) if use_cash else row["special_net"])
        row.update(group_ab=group_ab(row["ruleset"], R), sales_gross=sales_gross,
                   wholesale_gross=float(a["wholesale_gross"]) if a is not None else 0.0,
                   wholesale_share=float(a["wholesale_gross"]) / sales_gross if a is not None and sales_gross > 0 else None,
                   mgmt_n=int(a["mgmt_n"]) if a is not None else 0, mgmt_disc=mgmt, mgmt_inv_gross=mgmt_inv,
                   mgmt_inv_net_cash=float(a["mgmt_inv_net_cash"]) if a is not None else 0.0,
                   mgmt_inv_share=mgmt_inv / sales_gross if sales_gross > 0 else None,  # سهم این فاکتورها از فروش ناخالص
                   mgmt_rate=mgmt / mgmt_inv if mgmt_inv > 0 else None)               # نرخ تخفیف روی همان فاکتورها
        if v["type"] == "commission":
            _commission_visitor(row, R)
        else:
            _employed_visitor(row, tg, R)
        rows.append(row)

    sups = _supervisors({**plan, "supervisors": [s for s in plan.get("supervisors", []) if bkey(s["branch"]) not in excl]}, rows, R)
    unmatched = _unmatched(ms, keys)
    return {"visitors": rows, "supervisors": sups, "unmatched": unmatched,
            "branches": _branches(ms, mr, rows, plan, day_share)}


def _branches(ms: pd.DataFrame, mr: pd.DataFrame | None, rows: list[dict], plan: dict, day_share: float) -> list[dict]:
    """سطر هر شعبه: فروش همه فروشندگان شعبه و تارگت ریالی کل شعبه از فایل «تارگت ناخالص» شعبه‌ها.
    تارگت تعدادی گروه‌ها = جمع تارگت تعدادی ویزیتورهای شعبه در «ثبت تارگت» (از جمله ردیف‌های فایل استان که به
    ویزیتور فهرست وصل نشدند)؛ فقط تعدادی (تارگت ریالی گروه‌ها نمایش داده نمی‌شود)."""
    ms = ms.assign(b=ms["branch"].map(bkey))
    tq_sum: dict[str, dict[str, float]] = {}
    extra = [m for lst in (plan.get("target_missing") or {}).values() for m in lst]
    for b, groups in [(r["branch"], {g["key"]: g["target"] for g in r["groups"] if g["target"]}) for r in rows] +                      [(m["branch"], m.get("groups") or {}) for m in extra]:
        d = tq_sum.setdefault(bkey(b), {})
        for g, q in groups.items():
            d[g] = d.get(g, 0) + q
    rep = _report_metrics(ms, mr.assign(b=mr["branch"].map(bkey)) if mr is not None else None, ["b"])
    bt = plan.get("branch_targets") or {}
    gdef = {g["key"]: g for g in GROUPS}
    out = []
    for b, rp in rep.iterrows():
        if "هیبرید" not in b:
            continue
        gross = float(rp["gross"])
        t_file = (bt.get(b) or {}).get("rial")
        groups = []
        bs = ms[ms["b"] == b]
        for g in sorted(tq_sum.get(b) or {}, key=lambda k: GROUP_KEYS.index(k) if k in GROUP_KEYS else 99):
            tq = tq_sum[b][g]
            m = _group_mask(bs, gdef[g]) if g in gdef else None
            act_q = float(bs.loc[m, "qty"].sum()) if m is not None else None
            groups.append({"key": g, "qty": act_q, "target": tq, "target_day": tq * day_share,
                           "ach_day": act_q / (tq * day_share) if act_q is not None and tq else None})
        out.append({"branch": b, "req_net": float(rp["req_net"]), "gross": gross, "xnet": float(rp["xnet"]),
                    "qty": float(rp["qty"]), "customers": int(rp["customers"]),
                    "target_rial": t_file, "target_day": t_file * day_share if t_file else None,
                    "ach": gross / (t_file * day_share) if t_file else None, "groups": groups})
    return out


def _split_commission(row: dict, rate: float, special_rate: float | None) -> float:
    """فاکتورهای ویژه (عمده / با تخفیف مدیریتی) با نرخ ثابت پایه، بقیه مبنا با rate؛ اجزا در row ثبت می‌شوند.
    مبنا (base) = فروش خالص یا فروش خالص + تخفیف نقدی، طبق ماه. بقیه = مبنای ماه − مبنای فاکتورهای ویژه
    (برگشتی‌ها از بقیه کم شده‌اند)."""
    ws = row["special_base"] if special_rate is not None else 0.0
    rest = row["base"] - ws
    rest_comm, special_comm = rate * rest, (special_rate or 0) * ws
    comm = max(rest_comm + special_comm, 0.0)
    row.update(special_rate=special_rate, rest_net=rest, rest_commission=rest_comm, special_commission=special_comm,
               eff_rate=comm / row["base"] if row["base"] > 0 else None)
    return comm


def _commission_visitor(row: dict, R: dict):
    """سطح با فروش ناخالص تعیین می‌شود و نرخ سطح روی فروش خالص اعمال می‌شود (اعلام کاربر)."""
    C = R["commission"]
    tiers = R["rulesets"][row["ruleset"]]["visitor"]
    tier, rate = visitor_rate(row["gross"], tiers)
    comm = _split_commission(row, rate, C["wholesale_rate"])
    ftier, frate = visitor_rate(row["gross_forecast"], tiers)
    row.update(tier=tier, rate=rate, base_rate=rate, bonus_rate=0.0, extra_rate=0.0, commission=comm,
               reserve=comm * C["reserve"], payable=comm * (1 - C["reserve"]),
               forecast_tier=ftier, forecast_rate=frate,
               next_tier=(tiers[tier - 1][0] * M - row["gross"]) if tier < len(tiers) else None,
               status="سطح " + "۰۱۲۳۴۵۶۷۸۹"[tier])


def _employed_visitor(row: dict, tg: dict, R: dict):
    E = R["employed"]
    hit = [GROUPS[i] for i, g in enumerate(row["groups"])
           if not GROUPS[i].get("info") and g["ach"] is not None and g["ach"] >= E["group_min"]]
    bonus = sum(d["rate"] for d in hit if not d.get("extra"))
    extra = sum(d["rate"] for d in hit if d.get("extra"))
    bonus = min(bonus, E["group_cap"])
    row.update(bonus_rate=bonus, extra_rate=extra, groups_hit=len(hit), groups_set=len(tg))
    if row["target_rial"] is None:
        row.update(base_rate=None, rate=None, commission=None, reserve=0.0, payable=None, status="تارگت ریالی ثبت نشده")
        return
    base = next(r for upper, r in E["base"] if upper is None or row["ach"] < upper)
    rate = min(base + bonus, E["max_rate"]) + extra
    if row["base"] < E["floor"]:  # کف با مبنای پورسانت همان ماه
        row.update(base_rate=base, rate=0.0, commission=0.0, reserve=0.0, payable=0.0,
                   status="زیر کف ۷۰۰ میلیون تومان", floor_gap=E["floor"] - row["base"])
        return
    comm = _split_commission(row, rate, E["wholesale_rate"])
    row.update(base_rate=base, rate=rate, commission=comm, reserve=comm * E["reserve"], payable=comm * (1 - E["reserve"]),
               status=f"تحقق {round(row['ach'] * 100):d}٪".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))


def _supervisors(plan: dict, rows: list[dict], R: dict) -> list[dict]:
    teams: dict[tuple, list] = {}
    for r in rows:
        if r["supervisor"]:
            teams.setdefault((bkey(r["branch"]), r["supervisor"]), []).append(r)
    listed = [(bkey(s["branch"]), s["name"]) for s in plan.get("supervisors", [])]
    out = []
    for b, name in list(dict.fromkeys(listed + list(teams))):
        team = teams.get((b, name), [])
        rs = ruleset_of(b, R)
        rule = R["rulesets"][rs]["supervisor"]
        reserve = R["supervisor"]["reserve"]
        # تحقق تارگت سرپرست با فروش ناخالص تیم، پورسانت روی مبنای پورسانت تیم (فروش خالص یا خالص + نقدی؛ اعلام کاربر)
        net = sum(r["net"] for r in team)
        sales = sum(r["base"] for r in team)
        gross = sum(r["gross"] for r in team)
        fc = sum(r["base_forecast"] for r in team)
        gfc = sum(r["gross_forecast"] for r in team)
        comm = supervisor_commission(sales, rule, R["sup_rates"], reach=gross)
        target_sum = sum(r["target_rial"] or 0 for r in team)
        out.append({"id": f"{b}|{name}", "name": name, "branch": b, "ruleset": rs, "group_ab": group_ab(rs, R),
                    "visitors": len(team), "gross": gross,
                    "net": net, "net_cash": sum(r["net_cash"] for r in team), "base": sales,
                    "forecast": fc, "t1": rule["t1"] * M if rule else None, "t2": rule["t2"] * M if rule else None,
                    "ach_t1": gross / (rule["t1"] * M) if rule else None, "ach_t2": gross / (rule["t2"] * M) if rule else None,
                    "commission": comm, "forecast_commission": supervisor_commission(fc, rule, R["sup_rates"], reach=gfc),
                    "eff_rate": comm / sales if comm is not None and sales > 0 else None,
                    "reserve": comm * reserve if comm else 0.0,
                    "payable": comm * (1 - reserve) if comm is not None else None,
                    "target_rial": target_sum or None, "ach": sales / target_sum if target_sum else None,
                    "status": "بدون قاعده سرپرستی" if not rule else ("زیر تارگت اول" if gross < rule["t1"] * M
                              else "تارگت دوم" if gross >= rule["t2"] * M else "تارگت اول")})
    return out


REQUEST_DAYS_MIN = 0.80  # حداقل سهم روزهای دارای درخواست از روز کاری سپری‌شده (تصمیم کاربر)


def request_days(plan: dict, sales: pd.DataFrame, requests: pd.DataFrame | None, month: str, today: str | None) -> dict:
    """هشدار ثبت درخواست ویزیتورهای فهرست ماه: روز کاری سپری‌شده = روزهای غیرجمعه از اول ماه تا دیروز (امروز تمام نشده)؛
    روز فعال = هر روز تا دیروز (جمعه هم) که دست‌کم یک درخواست غیرباطل ثبت کرده. کمتر از ۸۰٪ روز کاری سپری‌شده = هشدار."""
    jy, jm = int(month[:4]), int(month[5:7])
    n = _month_len(jy, jm)
    last = int(today[8:10]) - 1 if today and today[:7] == month else (0 if today and today[:7] < month else n)
    elapsed = sum(1 for d in range(1, last + 1) if _j2g(jy, jm, d).weekday() != 4)
    cut = f"{month}/{last:02d}"
    excl = {bkey(b) for b in plan.get("excluded_branches") or []}
    visitors = [v for v in plan.get("visitors", []) if bkey(v["branch"]) not in excl]
    cols = ["seller_key", "seller", "seller_code", "branch"]
    both = pd.concat([sales[cols]] + ([requests[cols]] if requests is not None else []), ignore_index=True)
    match = match_sellers(visitors, both)
    days = pd.Series(dtype=int)
    if requests is not None and len(requests):
        mr = requests[requests["date"].str.startswith(month) & (requests["date"] <= cut)]
        days = mr.groupby("seller_key")["date"].nunique()
    branch_of = both.drop_duplicates("seller_key").set_index("seller_key")["branch"]
    rows = []
    for v in visitors:
        k = (match.get(v["id"]) or {}).get("key")
        nd = int(days.get(k, 0)) if k else 0
        rows.append({"id": v["id"], "name": v["name"], "code": v.get("code") or "", "branch": v["branch"],
                     "data_branch": str(branch_of.get(k, "")) if k else "", "supervisor": v.get("supervisor") or "",
                     "seller_key": k, "days": nd, "share": nd / elapsed if elapsed else None,
                     "low": bool(elapsed) and nd < REQUEST_DAYS_MIN * elapsed})
    return {"month": month, "elapsed": elapsed, "min_share": REQUEST_DAYS_MIN,
            "need": REQUEST_DAYS_MIN * elapsed, "visitors": rows}


def _unmatched(ms: pd.DataFrame, keys: set) -> list[dict]:
    """فروشندگان هیبرید دارای فروش در این ماه که در فهرست پورسانت نیستند."""
    o = ms[~ms["seller_key"].isin(keys) & ms["branch"].astype(str).str.contains("هیبرید")]
    if not len(o):
        return []
    g = o.groupby("seller_key").agg(name=("seller", "first"), code=("seller_code", "first"), branch=("branch", "first"),
                                    supervisor=("supervisor", "first"), net=("net", "sum"))
    g = g[g["net"] != 0].sort_values("net", ascending=False).reset_index().rename(columns={"seller_key": "key"})
    g["name"] = g["name"].map(clean_name)
    return [{k: (float(v) if k == "net" else str(v)) for k, v in r.items()} for r in g.to_dict("records")]

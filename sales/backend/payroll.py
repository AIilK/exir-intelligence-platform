"""حقوق ثابت فروشندگان استخدامی از ماژول حقوق و دستمزد کارآمد (فقط خواندن).

حقوق ثابت = حقوق پایه (کارکرد) + حق مسکن + بن خواربار + حق تأهل + حق اولاد + حق کارگری + اقلام ثابت حکم (مثل ایاب و ذهاب).
بهره‌وری (پورسانت)، اضافه‌کار، پاداش و کسورات جزو آن نیستند.
  - اگر فیش حقوق همان ماه در کارآمد محاسبه شده باشد: همان اقلام فیش (vwPR_Salary).
  - وگرنه برآورد از حکم کارگزینی فعال در آن ماه (vwPR_Duty): حقوق روزانه × روزهای ماه + مزایای ثابت جدول استخدامی
    + اقلام حکم (tblPR_DutyLines). همین فرمول فیش‌های ماه‌های کامل قبل را عیناً می‌سازد.
تطبیق ویزیتور با پرسنل: اول حساب تفصیلی (DLRef) ویزیتور در کارآمد، وگرنه نام در همان شعبه (فقط اگر یکتا باشد)."""
from __future__ import annotations

import re
import time

import pandas as pd

import commission as K

DUTY_SQL = """
SELECT d.ID AS duty, d.EmployeeRef AS emp, d.EmployeeCode AS emp_code, d.EmployeeName AS emp_name, d.BranchName AS branch,
       d.JobTitleName AS job, d.DateStart AS d_from, d.DateEnd AS d_to, d.Salary AS salary_m, d.SalaryDaily AS salary_d,
       d.SalaryType AS salary_type, d.RentSalarySingle AS rent_s, d.RentSalaryMarried AS rent_m,
       d.VictualSalarySingle AS victual_s, d.VictualSalaryMarried AS victual_m, d.MarriedSalary AS married,
       d.WorkerSalary AS worker, d.ChildSalary AS child, d.MaxNumberOfChildren AS child_max, d.NumOfChildren AS children,
       d.Marriage AS marriage, e.DLRef AS dl,
       (SELECT SUM(l.Salary) FROM dbo.tblPR_DutyLines l WHERE l.DutyRef = d.ID) AS lines
FROM dbo.vwPR_Duty d JOIN dbo.tblPR_Employee e ON e.ID = d.EmployeeRef
WHERE d.Status = 1 AND d.DateStart <= ? AND d.DateEnd >= ?"""  # همه شعب: بعضی ویزیتورهای هیبرید در حقوق «تهران - شرق» ثبت شده‌اند

SLIP_SQL = """
SELECT s.EmployeeRef AS emp, s.FunctionP AS base, s.FunctionD AS days, s.RentP AS rent, s.VictualP AS victual,
       s.MarriedP AS married, s.WorkerP AS worker, s.ChildP AS child, s.DutyLinesP AS lines
FROM dbo.vwPR_Salary s JOIN dbo.tblFiscalYear y ON y.ID = s.FiscalYear
WHERE y.Name = ? AND s.MonthRef = ?"""

VISITOR_DL_SQL = """
SELECT b.Name AS branch, v.Code AS code, v.DLRef AS dl
FROM dbo.tblVisitor v JOIN dbo.tblBranch b ON b.ID = v.BranchRef WHERE b.Name LIKE N'%هیبرید%'"""

SUPERVISOR_DL_SQL = """
SELECT b.Name AS branch, s.Name AS name, s.DLRef AS dl
FROM dbo.tblSupervisor s JOIN dbo.tblBranch b ON b.ID = s.BranchRef WHERE b.Name LIKE N'%هیبرید%'"""

PARTS = [("base", "حقوق پایه"), ("rent", "حق مسکن"), ("victual", "بن خواربار"), ("married", "حق تأهل"),
         ("child", "حق اولاد"), ("worker", "حق کارگری"), ("lines", "اقلام ثابت حکم")]
_STOP = {"آقای", "آقا", "خانم", "ویزیتور", "سرپرست", "هیبرید", "هیبریدی", "شرق", "غرب", "شمال", "جنوب"}


def _f(v) -> float:
    return float(v) if v is not None and pd.notna(v) else 0.0


def _from_duty(d, days: int) -> dict:
    married = int(_f(d.marriage)) == 1
    kids = min(int(_f(d.children)), int(_f(d.child_max)) or 0)
    return {"base": _f(d.salary_m) if d.salary_type else _f(d.salary_d) * days,
            "rent": _f(d.rent_m if married else d.rent_s), "victual": _f(d.victual_m if married else d.victual_s),
            "married": _f(d.married) if married else 0.0, "child": _f(d.child) * kids,
            "worker": _f(d.worker), "lines": _f(d.lines)}


def _words(s: str, branch: str) -> list[str]:
    drop = set(K.norm(branch).split()) | _STOP
    return [w for w in K.clean_name(s).replace("-", " ").split() if w not in drop and len(w) > 1]


def _squash(s) -> str:
    return re.sub(r"\s+", "", K.norm(s)).replace("آ", "ا")


def load(cn, month: str) -> dict:
    """داده خام یک ماه: حکم‌های فعال، فیش‌های همان ماه (اگر محاسبه شده) و حساب تفصیلی ویزیتورها."""
    jy, jm = int(month[:4]), int(month[5:7])
    days = K._month_len(jy, jm)
    start, end = K._j2g(jy, jm, 1), K._j2g(jy, jm, days)
    duty = pd.read_sql(DUTY_SQL, cn, params=[end, start])
    # چند حکم هم‌پوشان در یک ماه: آخرین حکم (تاریخ شروع دیرتر)
    duty = duty.sort_values(["emp", "d_from"]).drop_duplicates("emp", keep="last")
    slips = pd.read_sql(SLIP_SQL, cn, params=[str(jy), jm])
    vdl = pd.read_sql(VISITOR_DL_SQL, cn)
    sdl = pd.read_sql(SUPERVISOR_DL_SQL, cn)
    return {"month": month, "days": days, "duty": duty, "slips": slips, "vdl": vdl, "sdl": sdl}


def _find(duty, b: str, name: str, branch: str, dl):
    """(ردیف حکم، روش) یا (None، دلیل)."""
    if dl is not None and pd.notna(dl):
        c = duty[duty["dl"] == dl]
        if len(c) == 1:
            return c.iloc[0], "حساب تفصیلی"
    ws = _words(name, branch)
    if not ws:
        return None, "در حکم‌های فعال حقوق و دستمزد کارآمد پیدا نشد"
    same = duty[duty["b"] == b]
    c = same.iloc[:0]
    # ۱) همه کلمه‌های نام در نام پرسنل؛ ۲) همان بدون «ی» (سعیدیان / سعدیان)؛
    # ۳) برعکس: همه کلمه‌های نام پرسنل در نام فهرست (رنجبری / رنجبر)
    tests = [lambda n, f=f: all(f(w) in f(n) for w in ws) for f in (_squash, lambda x: _squash(x).replace("ی", ""))]
    tests.append(lambda n: all(_squash(w) in _squash(" ".join(ws)) for w in _words(n, branch)))
    for t in tests:
        c = same[same["emp_name"].map(t)]
        if len(c):
            break
    if len(c) == 1:
        return c.iloc[0], "نام"
    if len(c) > 1:
        return None, "چند پرسنل هم‌نام: " + "، ".join(c["emp_name"].map(K.norm))
    return None, "در حکم‌های فعال حقوق و دستمزد کارآمد پیدا نشد"


def _salary(hit, how: str, slips, days: int) -> dict:
    emp = int(hit["emp"])
    if emp in slips.index:
        s = slips.loc[emp]
        s = s.iloc[0] if isinstance(s, pd.DataFrame) else s
        parts, src = {k: _f(s[k]) for k, _ in PARTS}, "فیش حقوق"
    else:
        parts, src = _from_duty(hit, days), "حکم"
    return {"salary": sum(parts.values()), "salary_source": src, "salary_match": how,
            "salary_parts": [{"label": lb, "value": parts[k]} for k, lb in PARTS if parts[k]],
            "salary_emp": f"{K.norm(hit['emp_name'])} ({hit['emp_code']})", "salary_job": K.norm(hit["job"] or "")}


def match(raw: dict, visitors: list[dict], supervisors: list[dict] | None = None) -> tuple[dict, dict]:
    """(شناسه ویزیتور استخدامی ← حقوق ثابت، شناسه سرپرست «شعبه|نام» ← حقوق ثابت)؛ پیدانشده‌ها salary=None با دلیل.
    هر پرسنل فقط یک بار حقوق می‌گیرد: اگر سرپرست همان ویزیتور استخدامی باشد، حقوقش در ردیف ویزیتور است."""
    duty, slips = raw["duty"], raw["slips"].set_index("emp")
    duty = duty.assign(b=duty["branch"].map(K.bkey))
    vdl = {(K.bkey(b), str(c)): dl for b, c, dl in zip(raw["vdl"]["branch"], raw["vdl"]["code"], raw["vdl"]["dl"])}
    sdl: dict = {}
    for b, n, dl in zip(raw["sdl"]["branch"], raw["sdl"]["name"], raw["sdl"]["dl"]):
        sdl.setdefault(K.bkey(b), []).append((n, dl))
    used: dict[int, str] = {}

    def one(name, branch, dl, label):
        b = K.bkey(branch)
        hit, how = _find(duty, b, name, branch, dl)
        if hit is None:
            return {"salary": None, "salary_note": how}
        emp = int(hit["emp"])
        if emp in used:
            return {"salary": None, "salary_note": f"حقوق همین پرسنل ({K.norm(hit['emp_name'])}) در ردیف «{used[emp]}» آمده است"}
        used[emp] = label
        return _salary(hit, how, slips, raw["days"])

    vout = {v["id"]: one(v["name"], v["branch"], vdl.get((K.bkey(v["branch"]), str(v.get("code") or ""))), f"ویزیتور {v['name']}")
            for v in visitors if v.get("type") == "employed"}
    sout = {}
    for s in supervisors or []:
        b = K.bkey(s["branch"])
        # حساب تفصیلی سرپرست از جدول سرپرست کارآمد، اگر نامش (یکتا) با فهرست بخواند
        ws = _words(s["name"], s["branch"])
        cand = [dl for n, dl in sdl.get(b, []) if ws and all(_squash(w) in _squash(n) for w in ws)]
        sout[f"{b}|{s['name']}"] = one(s["name"], s["branch"], cand[0] if len(cand) == 1 else None, f"سرپرست {s['name']}")
    return vout, sout


class Cache:
    """داده حقوق هر ماه یک بار در هر ttl ثانیه از کارآمد خوانده می‌شود."""

    def __init__(self, connect, ttl: int = 900):
        self.connect, self.ttl, self.data = connect, ttl, {}

    def get(self, month: str) -> dict:
        hit = self.data.get(month)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        with self.connect() as cn:
            raw = load(cn, month)
        self.data[month] = (time.time(), raw)
        return raw

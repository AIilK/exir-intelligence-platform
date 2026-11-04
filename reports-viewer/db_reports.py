"""خواندن مستقیم پنج گزارش از دیتابیس راهکاران (فقط SELECT، اتصال Read-only).

کوئری‌ها طوری ساخته شده‌اند که دقیقاً همان ستون‌ها و ردیف‌های خروجی اکسل گزارش‌های راهکاران را بدهند
(با فایل‌های اکسل ۱۴۰۵/۰۷/۲۵–۲۶ ردیف‌به‌ردیف مقایسه شده‌اند).
تنظیمات اتصال از فایل .env پلتفرم اصلی خوانده می‌شود (REPORTS_ENV برای مسیر دیگر).
"""
import datetime as dt
import decimal
import os

import pyodbc

from jalali import jalali_date

ENV_PATH = os.environ.get("REPORTS_ENV") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend", ".env",
)


def _load_env(path):
    cfg = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def connect():
    cfg = _load_env(ENV_PATH)
    trust = "yes" if cfg.get("SQLSERVER_TRUST_CERTIFICATE", "true").lower() in ("1", "true", "yes") else "no"
    cs = (
        f"DRIVER={{{cfg.get('SQLSERVER_DRIVER', 'ODBC Driver 18 for SQL Server')}}};"
        f"SERVER={cfg['SQLSERVER_SERVER']};DATABASE={cfg['SQLSERVER_DATABASE']};"
        f"UID={cfg['SQLSERVER_USERNAME']};PWD={cfg['SQLSERVER_PASSWORD']};"
        f"Encrypt=yes;TrustServerCertificate={trust};ApplicationIntent=ReadOnly;"
    )
    conn = pyodbc.connect(cs, timeout=15, readonly=True)
    conn.timeout = 180
    return conn


# سال مالی جاری بر اساس تاریخ امروز
CURRENT_FY = """(SELECT TOP 1 FiscalYearRef FROM GNR3.LedgerFiscalYear
  WHERE GETDATE() >= StartDate AND GETDATE() < DATEADD(day, 1, EndDate) ORDER BY LedgerRef)"""

# اقلام اسناد انبار سال جاری که باطل نشده‌اند
def _voucher_items(extra_joins=""):
    return f"""
  FROM LGS3.InventoryVoucherItem i
  JOIN LGS3.InventoryVoucher v ON v.InventoryVoucherID = i.InventoryVoucherRef AND v.State <> 3
  JOIN LGS3.InventoryVoucherSpecification sp ON sp.InventoryVoucherSpecificationID = i.InventoryVoucherSpecificationRef
  JOIN LGS3.Part p ON p.PartID = i.PartRef{extra_joins}
  WHERE i.FiscalYearRef = {CURRENT_FY}"""


INVENTORY_BY_STORE = f"""
SELECT LTRIM(RTRIM(p.Code)) AS [کد کالا], LTRIM(RTRIM(p.Name)) AS [عنوان کالا],
       LTRIM(RTRIM(s.Code)) AS [کد انبار], LTRIM(RTRIM(s.Name)) AS [نام انبار],
       SUM(i.MajorUnitQuantity * CASE sp.Direction WHEN 1 THEN 1 ELSE -1 END) AS [موجودی تعدادی]
  {_voucher_items(chr(10) + "  JOIN LGS3.Store s ON s.StoreID = i.StoreRef")} AND sp.TypeOfEffectOnStock = 1
  GROUP BY p.Code, p.Name, s.Code, s.Name
  ORDER BY p.Code, s.Code"""

PURCHASE_REQUEST_OPEN = f"""
WITH di AS (
  SELECT di.DeliveryItemID, di.PurchaseRequestItemRef, di.MajorUnitQuantity
  FROM PRC3.DeliveryItem di JOIN PRC3.Delivery d ON d.DeliveryID = di.DeliveryRef WHERE d.State <> 3),
pm AS (
  SELECT p.ReceiptPermitItemID, di.PurchaseRequestItemRef
  FROM LGS3.ReceiptPermitItem p JOIN di ON p.ReferenceType = 4 AND p.ReferenceRef = di.DeliveryItemID),
iv AS (
  SELECT i.InventoryVoucherItemID, i.ReferenceType, i.ReferenceRef, sp.TypeOfEffectOnStock eff,
         i.MajorUnitQuantity * CASE sp.Direction WHEN 1 THEN 1 ELSE -1 END q
  FROM LGS3.InventoryVoucherItem i
  JOIN LGS3.InventoryVoucher v ON v.InventoryVoucherID = i.InventoryVoucherRef AND v.State <> 3
  JOIN LGS3.InventoryVoucherSpecification sp ON sp.InventoryVoucherSpecificationID = i.InventoryVoucherSpecificationRef
  WHERE i.ReferenceType IN (1, 2)),
tmp AS (SELECT iv.*, pm.PurchaseRequestItemRef FROM iv JOIN pm ON iv.ReferenceType = 2 AND iv.ReferenceRef = pm.ReceiptPermitItemID),
prm AS (
  SELECT q, PurchaseRequestItemRef FROM tmp WHERE eff = 1
  UNION ALL
  SELECT iv.q, t.PurchaseRequestItemRef FROM iv JOIN tmp t ON iv.ReferenceType = 1 AND iv.ReferenceRef = t.InventoryVoucherItemID WHERE iv.eff = 1),
sums AS (
  SELECT i.PurchaseRequestItemID,
    ISNULL((SELECT SUM(q) FROM tmp WHERE tmp.PurchaseRequestItemRef = i.PurchaseRequestItemID AND tmp.eff = 2), 0) t,
    ISNULL((SELECT SUM(q) FROM prm WHERE prm.PurchaseRequestItemRef = i.PurchaseRequestItemID), 0) pr,
    ISNULL((SELECT SUM(MajorUnitQuantity) FROM di WHERE di.PurchaseRequestItemRef = i.PurchaseRequestItemID), 0) d
  FROM PRC3.PurchaseRequestItem i)
SELECT CAST(NULL AS int) AS [Precision], i.PurchaseRequestItemID, pi.PurchaseItemID, r.RequestDate, r.Number,
  i.MajorUnitQuantity, i.DemandDate, i.MajorUnitQuantity AS PurchaseReqItmMUQty, u.Name AS UnitTitle,
  pl.Name AS RequestingCenterTitle, pi.PartRef AS PurchaseItemPartRef, pi.ServiceRef AS PurchaseItemServiceRef,
  p.Name AS PurchaseItemTitle, pi.Code AS PurchaseItemCode, i.State AS State, ISNULL(ap.FullName, '') AS PurchasingAgentTitle,
  mu.Name AS MajorUnit, p.MajorUnitRef, s.t AS Sum_InvntoryVoucherQuantityTemp, s.pr AS Sum_InvntoryVoucherQuantityPermanent,
  s.d AS Sum_DeliveryQuantity, r.RequestingCenterRef, ag.PartyRef AS PurchasingAgentPartyRef, i.State AS PurchaseRequestState,
  ISNULL(pd.Title, '') AS PurchasingDepartmentTitle, r.PurchasingDepartmentRef,
  CASE WHEN i.State = 6 THEN i.MajorUnitQuantity - s.d ELSE 0 END AS BlockQuantity
FROM PRC3.PurchaseRequestItem i
JOIN PRC3.PurchaseRequest r ON r.PurchaseRequestID = i.PurchaseRequestRef
JOIN sums s ON s.PurchaseRequestItemID = i.PurchaseRequestItemID
JOIN PRC3.PurchaseItem pi ON pi.PurchaseItemID = i.PurchaseItemRef
LEFT JOIN LGS3.Part p ON p.PartID = pi.PartRef
LEFT JOIN GNR3.Unit u ON u.UnitID = i.UnitRef
LEFT JOIN GNR3.Unit mu ON mu.UnitID = p.MajorUnitRef
LEFT JOIN LGS3.Plant pl ON pl.PlantID = r.RequestingCenterRef
LEFT JOIN PRC3.PurchasingAgent ag ON ag.PurchasingAgentID = i.PurchasingAgentRef
LEFT JOIN GNR3.Party ap ON ap.PartyID = ag.PartyRef
LEFT JOIN PRC3.PurchasingDepartment pd ON pd.PurchasingDepartmentID = r.PurchasingDepartmentRef
WHERE r.FiscalYearRef = {CURRENT_FY}
ORDER BY i.PurchaseRequestItemID"""

BOM_CONSUMPTION = """
WITH lines AS (
  SELECT n.PartRef, n.StandardConsumption, n.WastageConsumption, n.BillOfMaterialRef, n.ParentNodeRef, n.[Left] ord, 0 alt
  FROM CAC3.BillOfMaterialNode n WHERE n.ParentNodeRef IS NOT NULL
  UNION ALL
  SELECT a.PartRef, n.StandardConsumption * a.Ratio, n.WastageConsumption, n.BillOfMaterialRef, n.ParentNodeRef, n.[Left], a.Priority
  FROM CAC3.BillOfMaterialAlternativeNode a JOIN CAC3.BillOfMaterialNode n ON n.BillOfMaterialNodeID = a.BillOfMaterialNodeRef)
SELECT l.PartRef AS ConsumedPartRef, cp.Code AS ConsumedPartCode, cp.Name AS ConsumedPartName,
  b.Code AS FormulaCode, b.Title AS FormulaTitle, b.DecompositionQuantity AS FormulaDecompositionQuantity,
  CASE b.Status WHEN 1 THEN N'فعال' ELSE N'غيرفعال' END AS FormulaStatus,
  CASE WHEN b.IsMajor = 1 THEN N'اصلي' ELSE N'فرعي' END AS FormulaIsmager,
  l.StandardConsumption, l.WastageConsumption, pp.Code AS ParentNodeCode, pp.Name AS ParentNodeName,
  bp.Code AS ProducedPartCode, bp.Name AS ProducedPartName, b.PartRef AS ProducedPartRef, '' AS IsSideProduct
FROM lines l
JOIN CAC3.BillOfMaterial b ON b.BillOfMaterialID = l.BillOfMaterialRef
JOIN LGS3.Part cp ON cp.PartID = l.PartRef
JOIN CAC3.BillOfMaterialNode pn ON pn.BillOfMaterialNodeID = l.ParentNodeRef
JOIN LGS3.Part pp ON pp.PartID = pn.PartRef
JOIN LGS3.Part bp ON bp.PartID = b.PartRef
ORDER BY bp.Code, b.Code, l.ord, l.alt"""

# ستون‌های آنالیز تعدادی ← کد نوع سند انبار (منفی = کسر می‌شود)
ANALYSIS_COLUMNS = [
    ("ابتدای دوره", ["01", "01111", "-09999"]),
    ("خرید", ["02"]), ("برگشت خرید", ["55"]),
    ("برگشت از مصرف", ["05", "33"]), ("مصرف", ["51", "32"]),
    ("تولید", ["04"]), ("صادره به تولید", ["57"]), ("برگشت از تولید", ["20"]), ("مرجوعی به تولید", ["52"]),
    ("برگشت از فروش", ["18"]), ("تحویل فروش", ["69"]),
    ("رسید انتقال بین انبار", ["17"]), ("حواله انتقال بین انبار", ["68"]),
    ("دریافت امانی", ["23"]), ("ارسالی امانی", ["73"]), ("برگشت امانی", ["24"]), ("برگشت از دریافت امانی", ["74"]),
    ("برگشت از ضایعات", ["16"]), ("تحویل ضایعات", ["66"]),
    ("اضافات انبار گردانی", ["12"]), ("کسری انبارگردانی", ["62"]),
    ("رسید تبدیل کالا", ["19"]), ("حواله تبدیل کالا", ["70"]),
    ("رسید تغییر عامل", ["25"]), ("حواله تغییر عامل", ["75"]),
    ("سایر ورودیها", ["42", "34", "39", "44", "31", "9901"]),
    ("سایر خروجی ها", ["30", "41", "45", "35", "40", "43", "47", "9951"]),
]


def _analysis_sql():
    cols = []
    for title, codes in ANALYSIS_COLUMNS:
        parts = []
        for c in codes:
            sign = "-" if c.startswith("-") else ""
            parts.append(f"{sign}SUM(CASE WHEN x.code = '{c.lstrip('-')}' THEN x.q ELSE 0 END)")
        cols.append(f"{' + '.join(parts)} AS [{title}]")
    return f"""
WITH x AS (
  SELECT i.PartRef, LTRIM(RTRIM(sp.Code)) code, i.MajorUnitQuantity q, CASE sp.Direction WHEN 1 THEN 1 ELSE -1 END dir
  {_voucher_items()} AND sp.TypeOfEffectOnStock = 1)
SELECT CAST(0 AS int) AS [ردیف], p.Code AS [کد کالا], p.Name AS [نام کالا],
  ISNULL(p.TechnicalSpecification, '') AS TechnicalSpecification,
  CASE p.PartNature WHEN 1 THEN N'ماده اولیه' WHEN 2 THEN N'محصول نهایی' WHEN 3 THEN N'نیمه ساخته'
       WHEN 4 THEN N'دارایی ثابت' WHEN 5 THEN N'سایر' ELSE '' END AS PartNature,
  u.Name AS [نام واحد سنجش], '' AS [کد انبار], '' AS [نام انبار], '' AS [کد مرکز نگهداری], '' AS [نام مرکز نگهداری],
  CAST(0 AS int) AS PreviousQuantity,
  {', '.join(cols)},
  SUM(x.q * x.dir) AS [مانده], '' AS TrackingFactorComposition
FROM x JOIN LGS3.Part p ON p.PartID = x.PartRef LEFT JOIN GNR3.Unit u ON u.UnitID = p.MajorUnitRef
GROUP BY p.PartID, p.Code, p.Name, p.TechnicalSpecification, p.PartNature, u.Name
ORDER BY p.PartID"""


_RECEIPT_JOINS = """
  JOIN LGS3.Store s ON s.StoreID = i.StoreRef
  LEFT JOIN LGS3.PartUnit pu ON pu.PartUnitID = i.PartUnitRef
  LEFT JOIN GNR3.Unit mu ON mu.UnitID = p.MajorUnitRef
  LEFT JOIN SYS3.[User] us ON us.UserID = v.Creator
  LEFT JOIN GNR3.Party cp ON cp.PartyID = us.PartyRef
  OUTER APPLY (SELECT TOP 1 x.Name FROM LGS3.PartUnit x
               WHERE x.PartID = p.PartID AND x.UnitID <> p.MajorUnitRef ORDER BY x.PartUnitID) su"""

PRODUCTION_TEMP_RECEIPT = f"""
SELECT v.Number AS [شماره سند], sp.Name AS [نام سند], v.Date AS [تاریخ سند], s.Name AS [نام انبار],
  p.Code AS [کد کالا], p.Name AS [عنوان کالا], pu.Name AS [واحد], i.Quantity AS [مقدار],
  mu.Name AS [واحد اصلی], i.MajorUnitQuantity AS [مقدار به واحد اصلی],
  CASE WHEN i.SecondUnitQuantity IS NULL THEN '' ELSE ISNULL(su.Name, '') END AS [واحد دوم],
  i.SecondUnitQuantity AS [مقدار به واحد دوم], v.CounterpartEntityText AS [طرف مقابل], v.State AS [وضعیت],
  ISNULL(i.Description, '') AS [توضیحات], cp.FullName AS [صادر کننده], ISNULL(i.ReferenceCode, '') AS [شماره عطف]
  {_voucher_items(_RECEIPT_JOINS)} AND LTRIM(RTRIM(sp.Code)) = '28'
  ORDER BY v.Number DESC, i.RowNumber"""

ISSUE_PERMIT_SALES = f"""
WITH passed AS (
  SELECT iv.ReferenceRef, SUM(iv.MajorUnitQuantity * CASE sp.Direction WHEN 2 THEN 1 ELSE -1 END) q
  FROM LGS3.InventoryVoucherItem iv
  JOIN LGS3.InventoryVoucher v ON v.InventoryVoucherID = iv.InventoryVoucherRef AND v.State <> 3
  JOIN LGS3.InventoryVoucherSpecification sp ON sp.InventoryVoucherSpecificationID = iv.InventoryVoucherSpecificationRef
  WHERE iv.ReferenceType = 4
  GROUP BY iv.ReferenceRef)
SELECT N'حواله فروش' AS [مبنای مجوز], N'قلم حواله فروش' AS [مبنای قلم], o.Number AS [شماره مبنا], p.Number AS [شماره],
  p.Date AS [تاریخ], b.Title AS [شعبه], pl.Name AS [مرکز نگهداری], s.Name AS [انبار],
  CASE p.CounterpartEntityCode WHEN 238 THEN N'شخص/شرکت' ELSE '' END AS [نوع طرف مقابل],
  p.CounterpartEntityText AS [طرف مقابل], rp.FullName AS [تحویل گیرنده/دهنده], pi.State AS [وضعیت],
  pt.Code AS [کد کالا], pt.Name AS [نام کالا], u.Name AS [واحد سنجش],
  pi.Quantity AS [مقدار], pi.MajorUnitQuantity AS [مقدار به واحد اصلی],
  ISNULL(ps.q, 0) * pi.Quantity / NULLIF(pi.MajorUnitQuantity, 0) AS [مقدار پاس شده],
  ISNULL(ps.q, 0) AS [مقدار پاس شده به واحد اصلی],
  pi.Quantity - ISNULL(ps.q, 0) * pi.Quantity / NULLIF(pi.MajorUnitQuantity, 0) AS [مانده],
  pi.MajorUnitQuantity - ISNULL(ps.q, 0) AS [مانده به واحد اصلی]
FROM LGS3.IssuePermitItem pi
JOIN LGS3.IssuePermit p ON p.IssuePermitID = pi.IssuePermitRef
JOIN SLS3.[Order] o ON p.ReferenceType = 8 AND o.OrderID = p.ReferenceRef
LEFT JOIN GNR3.Branch b ON b.BranchID = p.BranchRef
LEFT JOIN LGS3.Plant pl ON pl.PlantID = p.PlantRef
LEFT JOIN LGS3.Store s ON s.StoreID = p.StoreRef
LEFT JOIN GNR3.Party rp ON rp.PartyID = p.RecipientRef
JOIN LGS3.Part pt ON pt.PartID = pi.PartRef
LEFT JOIN GNR3.Unit u ON u.UnitID = pi.UnitRef
LEFT JOIN passed ps ON ps.ReferenceRef = pi.IssuePermitItemID
WHERE p.FiscalYearRef = {CURRENT_FY}
ORDER BY p.Date DESC, p.Number DESC, pi.RowNumber DESC"""

ISSUE_PERMIT_STATES = {1: "تحویل نشده", 3: "در حال تحویل", 4: "تحویل شده"}
PURCHASE_STATES = {1: "ثبت شده", 3: "تاييد شده", 4: "در جريان", 6: "متوقف شده", 7: "بسته شده"}
VOUCHER_STATES = {1: "ثبت شده", 2: "تایید شده", 3: "باطل شده"}

# کلید = نام فایل اکسل منبع (همان SOURCES در app.py)
REPORTS = {
    "گزارش موجودی کالا به تفکیک انبار": {"sql": INVENTORY_BY_STORE},
    "مانده باز درخواست خرید بر اساس رسید انبار": {
        "sql": PURCHASE_REQUEST_OPEN, "dates": ["RequestDate", "DemandDate"], "labels": {"State": PURCHASE_STATES}},
    "مصرف کالا در محصول و نیمه ساخته": {"sql": BOM_CONSUMPTION},
    "آنالیز تعدادی": {"sql": _analysis_sql(), "rownum": "ردیف"},
    "رسید موقت تولید": {
        "sql": PRODUCTION_TEMP_RECEIPT, "dates": ["تاریخ سند"], "labels": {"وضعیت": VOUCHER_STATES}},
    "مروراسنادی-مجوز خروج-حواله": {
        "sql": ISSUE_PERMIT_SALES, "dates": ["تاریخ"], "labels": {"وضعیت": ISSUE_PERMIT_STATES}},
}


def _clean(v):
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, str):
        return v.strip()
    return v


def fetch(base_name):
    """(columns, rows) گزارش را مستقیم از دیتابیس برمی‌گرداند."""
    spec = REPORTS[base_name]
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(spec["sql"])
        columns = [d[0] for d in cur.description]
        raw = cur.fetchall()
    date_idx = [columns.index(c) for c in spec.get("dates", [])]
    labels = {columns.index(c): m for c, m in spec.get("labels", {}).items()}
    rows = []
    for r in raw:
        row = [_clean(v) for v in r]
        for i in date_idx:
            if row[i] is not None:
                row[i] = jalali_date(row[i])
        for i, m in labels.items():
            row[i] = m.get(row[i], row[i])
        rows.append(row)
    if spec.get("rownum"):
        ri = columns.index(spec["rownum"])
        for n, row in enumerate(rows, 1):
            row[ri] = n
    return columns, rows

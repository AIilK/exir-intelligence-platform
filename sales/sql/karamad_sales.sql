/* =====================================================================
   داده‌های گزارش «Hybrid Sales report» از دیتابیس کارآمد (KDB روی 192.168.10.210)
   همان کوئری‌هایی که داشبورد (backend/sql_source.py) لایو اجرا می‌کند.
   نگاشت شیت‌های اکسل:
     Sheet          ← dbo.vwFactorFBLinesFull  (فروش + برگشت از فروش، هر سطر یک کالا)
     درخواست        ← dbo.vwFactorDLinesFull   (FactorStatus: 0 درخواست، 1 فاکتور شده، 2 باطل شده)
     لیست مشتریان   ← dbo.tblCustomer (+ tblBranch, tblCity, tblGuild, tblGrade, tblPaymentType, tblCustomerCredit)
   نکته: شناسه فاکتور فروش (tblFactorF.ID) و برگشتی (tblFactorB.ID) جداگانه شماره می‌خورند؛
         کلید یکتا = نوع فاکتور + شناسه.
   ===================================================================== */
USE KDB;

DECLARE @month  nvarchar(7)  = N'1405/07';   -- ماه شمسی
DECLARE @branch nvarchar(50) = N'هیبرید';    -- فقط شعبه‌هایی که نامشان این را دارد ('' = همه)
DECLARE @from date, @to date;
SELECT @from = MIN(GregorianDate), @to = MAX(GregorianDate)
FROM dbo.tblCalendar WHERE PersianDate LIKE @month + N'/%';


/* ۱) فاکتورهای فروش و برگشت از فروش — معادل شیت «Sheet» ------------------ */
SELECT
  v.PersianDate     AS [تاریخ],
  v.FactorType      AS [نوع فاکتور],        -- فروش / برگشت از فروش
  v.BranchCode      AS [کد شعبه],     v.BranchName     AS [نام شعبه],
  v.SupervisorCode  AS [کد سرپرست],   v.SupervisorName AS [نام سرپرست],
  v.VisitorCode     AS [کد فروشنده],  v.VisitorName    AS [نام فروشنده],
  v.LineName        AS [نام لاین],    v.RouteName      AS [نام مسیر],   v.CityName AS [نام شهر],
  v.GoodsCode       AS [کد کالا],     v.GoodsName      AS [نام کالا],
  v.BrandName       AS [نام برند],    v.CategoryName   AS [نام گروه کالا],
  v.PaymentTypeName AS [نحوه پرداخت],
  v.Code            AS [شماره],       v.ID             AS [شناسه فاکتور], v.FactorDCode AS [شماره مرجع],
  v.CustomerCode    AS [کد مشتری],    v.CustomerName   AS [نام مشتری],
  v.TotalT          AS [مجموع تعداد],
  v.Price           AS [فی فروش],
  v.SumPrice        AS [جمع قبل تخفیف],
  v.Discount        AS [تخفیف حجمی],
  v.CashDiscount    AS [تخفیف نقدی],
  v.Vat             AS [ارزش افزوده],
  v.PriceP          AS [قابل پرداخت]
FROM dbo.vwFactorFBLinesFull v
WHERE v.DateE BETWEEN @from AND @to
  AND v.BranchName LIKE N'%' + @branch + N'%'
ORDER BY v.DateE, v.BranchName, v.Code;


/* ۲) درخواست‌ها — معادل شیت «درخواست» ------------------------------------- */
SELECT
  c.PersianDate     AS [تاریخ],
  v.FactorStatus    AS [وضعیت درخواست],    -- 0 درخواست، 1 فاکتور شده
  v.FactorStatusName,
  v.BranchName      AS [نام شعبه],    v.SupervisorName AS [نام سرپرست],
  v.VisitorCode     AS [کد فروشنده],  v.VisitorName    AS [نام فروشنده],
  v.GoodsCode       AS [کد کالا],     v.GoodsName      AS [نام کالا],
  v.BrandName       AS [نام برند],    v.CategoryName   AS [نام گروه کالا],
  v.Code            AS [شماره],       v.ID             AS [شناسه فاکتور],
  v.CustomerCode    AS [کد مشتری],    v.CustomerName   AS [نام مشتری],
  v.TotalT          AS [مجموع تعداد], v.SumPrice       AS [جمع قبل تخفیف],
  v.Discount        AS [تخفیف حجمی],  v.Vat            AS [ارزش افزوده], v.PriceP AS [قابل پرداخت]
FROM dbo.vwFactorDLinesFull v
JOIN dbo.tblCalendar c ON c.GregorianDate = v.DateE
WHERE v.DateE BETWEEN @from AND @to
  AND v.BranchName LIKE N'%' + @branch + N'%'
  AND v.FactorStatus <> 2                       -- باطل‌شده‌ها حذف
ORDER BY v.DateE, v.BranchName, v.Code;


/* ۳) لیست مشتریان فعال — معادل شیت «لیست مشتریان» ------------------------ */
SELECT b.Name AS [شعبه], c.Code AS [کد], c.Name AS [نام کامل], ci.Name AS [شهر],
       g.Name AS [صنف], gr.Name AS [گرید], c.RFMScore AS [امتیاز RFM], cr.Credit AS [اعتبار],
       c.Status AS [وضعیت مشتری], pt.Name AS [نحوه پرداخت]
FROM dbo.tblCustomer c
JOIN dbo.tblBranch b ON b.ID = c.BranchRef
LEFT JOIN dbo.tblCity ci ON ci.ID = c.CityRef
LEFT JOIN dbo.tblGuild g ON g.ID = c.GuildRef
LEFT JOIN dbo.tblGrade gr ON gr.ID = c.GradeRef
LEFT JOIN dbo.tblPaymentType pt ON pt.ID = c.PaymentTypeRef
LEFT JOIN (SELECT CustomerRef, MAX(Credit) AS Credit FROM dbo.tblCustomerCredit GROUP BY CustomerRef) cr
       ON cr.CustomerRef = c.ID
WHERE c.Status = 1 AND b.Name LIKE N'%' + @branch + N'%';


/* ۴) خلاصه روزانه هر شعبه (برای چک سریع با گزارش‌ها) ----------------------- */
SELECT v.PersianDate AS [تاریخ], v.BranchName AS [شعبه],
       COUNT(DISTINCT CASE WHEN v.FactorType = N'فروش' THEN v.ID END) AS [تعداد فاکتور],
       SUM(CASE WHEN v.FactorType = N'فروش' THEN 1 ELSE -1 END * (v.SumPrice - v.Discount - v.CashDiscount)) AS [فروش خالص]
FROM dbo.vwFactorFBLinesFull v
WHERE v.DateE BETWEEN @from AND @to AND v.BranchName LIKE N'%' + @branch + N'%'
GROUP BY v.PersianDate, v.BranchName
ORDER BY v.PersianDate, [فروش خالص] DESC;


/* ۵) روزهای کاری ماه (به‌جز جمعه) و سپری‌شده تا دیروز ---------------------- */
SELECT SUM(CASE WHEN PersianWeekName <> N'جمعه' THEN 1 ELSE 0 END) AS [کل روز کاری],
       SUM(CASE WHEN PersianWeekName <> N'جمعه' AND GregorianDate < CAST(GETDATE() AS date) THEN 1 ELSE 0 END) AS [سپری‌شده]
FROM dbo.tblCalendar WHERE PersianDate LIKE @month + N'/%';


/* ۶) جدول‌های پایه، اگر بخواهید بدون ویو کار کنید -------------------------------
   tblFactorF / tblFactorFLines / tblFactorfDiscount   فاکتور فروش، سطرها، ریز تخفیف
   tblFactorB / tblFactorBLines                         برگشت از فروش
   tblFactorD / tblFactorDLines                         درخواست
   tblCustomer, tblVisitor, tblSupervisor, tblLine, tblRouteVisit, tblBranch,
   tblGoods, tblAccDiscount, tblPaymentType, tblCalendar (تبدیل تاریخ شمسی)       */

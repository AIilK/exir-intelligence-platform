/*
    Exir Kadous - Treasury schema discovery

    این فایل فقط دستورات خواندنی SELECT دارد.
    آن را داخل دیتابیس واقعی راهکاران اجرا کنید و Resultها را ذخیره کنید.
    نام کاربری، رمز عبور یا Connection String را ارسال نکنید.
*/

SET NOCOUNT ON;

-- 1) اطمینان از دیتابیس و دسترسی فعلی
SELECT
    DB_NAME() AS database_name,
    SUSER_SNAME() AS login_name,
    USER_NAME() AS database_user;

-- 2) جدول‌های احتمالی مرتبط با خزانه در FIN3
SELECT
    t.TABLE_SCHEMA AS schema_name,
    t.TABLE_NAME AS table_name
FROM INFORMATION_SCHEMA.TABLES AS t
WHERE t.TABLE_TYPE = 'BASE TABLE'
  AND t.TABLE_SCHEMA = 'FIN3'
  AND (
        t.TABLE_NAME LIKE '%Account%'
     OR t.TABLE_NAME LIKE '%Bank%'
     OR t.TABLE_NAME LIKE '%Cash%'
     OR t.TABLE_NAME LIKE '%Cheque%'
     OR t.TABLE_NAME LIKE '%Check%'
     OR t.TABLE_NAME LIKE '%Receipt%'
     OR t.TABLE_NAME LIKE '%Payment%'
     OR t.TABLE_NAME LIKE '%Settlement%'
     OR t.TABLE_NAME LIKE '%Statement%'
  )
ORDER BY t.TABLE_NAME;

-- 3) ستون‌های سه جدول کاندید فعلی
SELECT
    c.TABLE_SCHEMA AS schema_name,
    c.TABLE_NAME AS table_name,
    c.ORDINAL_POSITION AS column_order,
    c.COLUMN_NAME AS column_name,
    c.DATA_TYPE AS data_type,
    c.CHARACTER_MAXIMUM_LENGTH AS max_length,
    c.NUMERIC_PRECISION AS numeric_precision,
    c.NUMERIC_SCALE AS numeric_scale,
    c.IS_NULLABLE AS is_nullable
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_SCHEMA = 'FIN3'
  AND c.TABLE_NAME IN (
      'Account',
      'AccountDebitCreditStatement',
      'AccountDebitCreditStatementItem'
  )
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;

-- 4) کلیدهای اصلی سه جدول کاندید
SELECT
    k.TABLE_SCHEMA AS schema_name,
    k.TABLE_NAME AS table_name,
    k.COLUMN_NAME AS primary_key_column,
    k.ORDINAL_POSITION AS key_order
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS k
    ON k.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
   AND k.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
  AND k.TABLE_SCHEMA = 'FIN3'
  AND k.TABLE_NAME IN (
      'Account',
      'AccountDebitCreditStatement',
      'AccountDebitCreditStatementItem'
  )
ORDER BY k.TABLE_NAME, k.ORDINAL_POSITION;

-- 5) ارتباط‌های واقعی سه جدول کاندید با سایر جدول‌ها
SELECT
    OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS source_schema,
    OBJECT_NAME(fkc.parent_object_id) AS source_table,
    COL_NAME(
        fkc.parent_object_id,
        fkc.parent_column_id
    ) AS source_column,
    OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS target_schema,
    OBJECT_NAME(fkc.referenced_object_id) AS target_table,
    COL_NAME(
        fkc.referenced_object_id,
        fkc.referenced_column_id
    ) AS target_column
FROM sys.foreign_key_columns AS fkc
WHERE (
       OBJECT_SCHEMA_NAME(fkc.parent_object_id) = 'FIN3'
   AND OBJECT_NAME(fkc.parent_object_id) IN (
       'Account',
       'AccountDebitCreditStatement',
       'AccountDebitCreditStatementItem'
   )
)
OR (
       OBJECT_SCHEMA_NAME(fkc.referenced_object_id) = 'FIN3'
   AND OBJECT_NAME(fkc.referenced_object_id) IN (
       'Account',
       'AccountDebitCreditStatement',
       'AccountDebitCreditStatementItem'
   )
)
ORDER BY source_schema, source_table, source_column;

-- 6) تعداد رکوردها؛ برای تشخیص جدول واقعی بدون دریافت محتوای محرمانه
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    SUM(p.rows) AS approximate_row_count
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id
INNER JOIN sys.partitions AS p
    ON p.object_id = t.object_id
   AND p.index_id IN (0, 1)
WHERE s.name = 'FIN3'
  AND t.name IN (
      'Account',
      'AccountDebitCreditStatement',
      'AccountDebitCreditStatementItem'
  )
GROUP BY s.name, t.name
ORDER BY t.name;

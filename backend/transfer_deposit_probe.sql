USE [Exir_sg3];
GO

-- 1) ستون‌های جدول انتقال داخلی حساب‌های بانکی
SELECT
    c.column_id AS column_order,
    c.name AS column_name,
    TYPE_NAME(c.user_type_id) AS data_type,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable
FROM sys.columns AS c
WHERE c.object_id = OBJECT_ID(N'RPA3.TransferDeposit')
ORDER BY c.column_id;

-- 2) ارتباط‌های جدول با سایر جداول راهکاران
SELECT
    fk.name AS foreign_key_name,
    COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS source_column,
    OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS target_schema,
    OBJECT_NAME(fkc.referenced_object_id) AS target_table,
    COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS target_column
FROM sys.foreign_keys AS fk
INNER JOIN sys.foreign_key_columns AS fkc
    ON fkc.constraint_object_id = fk.object_id
WHERE fk.parent_object_id = OBJECT_ID(N'RPA3.TransferDeposit')
ORDER BY source_column;

-- 3) نمونه داده برای تشخیص حساب مبدأ، مقصد، تاریخ، مبلغ و شماره سند
SELECT TOP (50)
    *
FROM RPA3.TransferDeposit;
GO

from app.query.sql_validator import SQLValidator


validator = SQLValidator()


tests = [

    "SELECT TOP 10 * FROM dbo.customers",

    "SELECT id, name FROM dbo.customers",

    "DELETE FROM dbo.customers",

    "UPDATE dbo.customers SET city = N'تهران'",

    "DROP TABLE dbo.customers",

    "SELECT * FROM dbo.customers; DELETE FROM dbo.customers",

]


for sql in tests:

    result = validator.validate(sql)

    print()
    print("=" * 60)
    print("SQL:")
    print(sql)

    print()

    print("RESULT:")
    print(result)
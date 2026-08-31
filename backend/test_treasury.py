from app.services.treasury_service import (
    get_account_balance,
    get_account_transactions,
    get_cheque_due_report,
    get_latest_issued_cheques,
    get_latest_payments,
    get_latest_received_cheques,
    get_latest_receipts,
    get_received_cheques_by_status,
    get_receivable_report
)


print("------ BALANCE ------")

result = get_account_balance("آبرام")

print(result)



print("------ TRANSACTIONS ------")

result = get_account_transactions(
    account_id=2201,
    limit=5,
)

for item in result.get("transactions", []):
    print(item)



print("------ RECEIVABLE ------")

result = get_receivable_report()

print(result)


print("------ LATEST RECEIPTS ------")

result = get_latest_receipts(limit=5)

for item in result.get("documents", []):
    print(item)


print("------ RECEIVED CHEQUES DUE IN 30 DAYS ------")

result = get_cheque_due_report(
    cheque_type="received",
    days=30,
    limit=5,
)

for item in result.get("cheques", []):
    print(item)


print("------ OVERDUE ISSUED CHEQUES ------")

result = get_cheque_due_report(
    cheque_type="issued",
    overdue=True,
    limit=5,
)

for item in result.get("cheques", []):
    print(item)


print("------ PROTESTED RECEIVED CHEQUES ------")

result = get_received_cheques_by_status(
    cheque_status="protested",
    limit=5,
)

for item in result.get("cheques", []):
    print(item)


print("------ LATEST RECEIVED CHEQUES ------")

result = get_latest_received_cheques(limit=5)

for item in result.get("cheques", []):
    print(item)


print("------ LATEST ISSUED CHEQUES ------")

result = get_latest_issued_cheques(limit=5)

for item in result.get("cheques", []):
    print(item)


print("------ LATEST PAYMENTS ------")

result = get_latest_payments(limit=5)

for item in result.get("documents", []):
    print(item)

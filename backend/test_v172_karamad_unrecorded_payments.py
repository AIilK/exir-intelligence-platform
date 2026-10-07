from app.services.karamad_unrecorded_payment_service import _name_score, invoice_codes, is_internal_funding


def test_invoice_codes_reads_listed_invoices():
    assert invoice_codes("فاکتور 1145 و 1146و1147و1163") == {"1145", "1146", "1147", "1163"}
    assert invoice_codes("فاکتور 515-604-514") == {"515", "604", "514"}


def test_invoice_codes_ignores_dates_years_and_long_ids():
    assert invoice_codes("بابت فاکتور های مورخ 1405/04/17") == set()
    assert invoice_codes("واریزی نامشخص(شماره فاکتور 50358006)") == set()
    assert invoice_codes("اعلامیه شناسه 203141-چک برگشتی 1404") == set()


def test_internal_funding_is_not_customer_money():
    assert is_internal_funding("دریافت از جاری شرکا", "")
    assert is_internal_funding("دریافت از کادوس", "")
    assert not is_internal_funding("واریزی نامشخص(هادی بیات)", "")


def test_name_score_ignores_generic_shop_words():
    assert _name_score("هادی بیات- گالری لایت", "بابت واریزی نامشخص(هادی بیات)") >= 0.6
    assert _name_score("گالری لایت", "گالری") == 0  # a generic word alone never matches

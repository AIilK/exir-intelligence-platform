from app.services.liquidity.account_map import classify


def _pair(result):
    return result.section, result.category, result.sign


def test_customer_collections_are_the_only_averaged_inflow():
    assert _pair(classify("rahkaran", "inflow", "123003")) == ("inflow", "customer_collection", 1)
    assert _pair(classify("rahkaran", "inflow", "123011")) == ("inflow", "customer_collection", 1)
    assert _pair(classify("karamad", "inflow", 1313)) == ("inflow", "customer_collection", 1)
    assert _pair(classify("rahkaran", "inflow", "717012")) == ("inflow", "other_operating_inflow", 1)


def test_inter_bank_transfers_are_never_counted():
    # «شرکتی» counterparty overrides its account (جاری شرکا 512029).
    assert _pair(classify("rahkaran", "inflow", "512029", "950028")) == ("excluded", "inter_bank", 1)
    assert _pair(classify("rahkaran", "outflow", "512029", "950028")) == ("excluded", "inter_bank", 1)
    assert _pair(classify("karamad", "outflow", "1113")) == ("excluded", "inter_bank", 1)
    assert _pair(classify("rahkaran", "outflow", "126001")) == ("excluded", "inter_bank", 1)


def test_shareholders_and_loans_are_financing_but_installments_are_outflow():
    assert _pair(classify("rahkaran", "inflow", "512029", "950031")) == ("financing", "shareholders", 1)
    assert _pair(classify("rahkaran", "outflow", "512029")) == ("financing", "shareholders", 1)
    assert _pair(classify("karamad", "inflow", "3701")) == ("financing", "shareholders", 1)
    assert _pair(classify("rahkaran", "inflow", "412001")) == ("financing", "loan", 1)
    assert _pair(classify("rahkaran", "outflow", "412001")) == ("outflow", "loan_installments", 1)


def test_currency_blocking_is_imports_net_of_returns():
    assert _pair(classify("rahkaran", "outflow", "116001")) == ("outflow", "imports", 1)
    assert _pair(classify("rahkaran", "inflow", "116001")) == ("outflow", "imports", -1)


def test_hybrid_stock_settlement_is_internal_on_both_sides():
    # Karamad: the hybrid pays the group firms (پادینا، مولهنس، …) for its stock.
    assert _pair(classify("karamad", "outflow", "3112")) == ("internal", "hybrid_settlement", 1)
    # Rahkaran: the same money arrives as a customer receipt from «هیبرید …».
    assert _pair(classify("rahkaran", "inflow", "123003", "999", "هیبرید غرب (پادینا)- تهران")) == (
        "internal", "hybrid_settlement", 1)
    assert _pair(classify("rahkaran", "inflow", "123003", "999", ". هيبريد مازندران - کالیون")) == (
        "internal", "hybrid_settlement", 1)
    # A B2B customer stays a customer collection.
    assert _pair(classify("rahkaran", "inflow", "123003", "999", "شرکت الف")) == (
        "inflow", "customer_collection", 1)
    # A hybrid counterparty on an excluded account keeps the exclusion.
    assert _pair(classify("rahkaran", "inflow", "123001", "999", "هیبرید اصفهان")) == (
        "excluded", "cheque_section", 1)


def test_cheque_cash_ins_are_counted_only_in_the_cheque_sections():
    assert _pair(classify("karamad", "inflow", "1313", note="cheque_collection")) == ("excluded", "cheque_section", 1)
    assert _pair(classify("rahkaran", "inflow", None, note="cheque_collection")) == ("excluded", "cheque_section", 1)
    assert _pair(classify("rahkaran", "inflow", "123003", "1", "هیبرید اصفهان", note="cheque_collection")) == (
        "excluded", "cheque_section", 1)


def test_fx_bought_by_the_hybrid_for_the_company_is_imports():
    assert _pair(classify("karamad", "outflow", "3112", note="fx_purchase")) == ("outflow", "imports", 1)


def test_payroll_counted_once_and_karamad_payroll_ignored():
    assert _pair(classify("rahkaran", "outflow", "512002")) == ("excluded", "payroll_section", 1)
    assert _pair(classify("karamad", "outflow", "3220")) == ("excluded", "karamad_payroll_ignored", 1)
    assert _pair(classify("karamad", "outflow", "3216")) == ("excluded", "karamad_payroll_ignored", 1)


def test_petty_cash_staff_advances_and_expense_fallbacks():
    assert _pair(classify("rahkaran", "outflow", "126005")) == ("outflow", "petty_cash", 1)
    assert _pair(classify("rahkaran", "outflow", "124003")) == ("outflow", "personnel_other", 1)
    assert _pair(classify("rahkaran", "outflow", "712010")) == ("outflow", "freight", 1)
    assert _pair(classify("rahkaran", "outflow", "713008")) == ("outflow", "admin", 1)
    assert _pair(classify("karamad", "outflow", "8315")) == ("outflow", "admin", 1)


def test_unknown_accounts_go_to_review_never_to_a_total():
    assert _pair(classify("rahkaran", "inflow", "512025")) == ("review", "unknown_deposit", 1)
    assert _pair(classify("karamad", "inflow", "9512")) == ("review", "unknown_deposit", 1)
    assert _pair(classify("rahkaran", "outflow", "999999")) == ("review", "unmapped", 1)
    assert _pair(classify("rahkaran", "inflow", None)) == ("review", "unmapped", 1)
    assert _pair(classify("karamad", "inflow", "8315")) == ("review", "unmapped", 1)

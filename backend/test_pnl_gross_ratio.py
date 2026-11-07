from app.services import pnl_live_service as service


def _report():
    rep = service.Report(["A", "B"])
    rep.add("Gross Sales (Mrials)", {"A": 800.0, "B": 200.0}, canon="gross")
    rep.add("Discounts", {"A": 100.0, "B": 50.0}, canon="discount", ratio_base="gross")
    rep.add("Return", {"A": 100.0}, canon="return")
    rep.add("Total Net Sales", {"A": 600.0, "B": 150.0}, kind="total", canon="net")
    rep.add("سربار تولید", {"A": 60.0, "B": 15.0}, group="cogs_std")
    rep.add("cost of goods sold", {"A": 300.0}, canon="cogs")
    return rep


def _by_label(rows):
    return {r["label"]: r for r in rows}


def test_discount_ratio_uses_gross_sales():
    rows = _by_label(_report().finish())
    assert rows["Discounts"]["periods"]["p0"]["ratio"] == 150 / 1000


def test_other_rows_keep_net_sales_ratio():
    rows = _by_label(_report().finish())
    assert rows["سربار تولید"]["periods"]["p0"]["ratio"] == 75 / 750
    assert rows["cost of goods sold"]["periods"]["p0"]["ratio"] == 300 / 750
    assert rows["Gross Sales (Mrials)"]["periods"]["p0"]["ratio"] == 1000 / 750


def test_conversion_pools_split_labour_and_overhead():
    rows = [
        {"gl": "7110", "dl": "500001", "kind": 2, "amount": 100},   # دستمزد مرکز تولیدی
        {"gl": "7190", "dl": "500002", "kind": 1, "amount": 20},    # 7190 طبق راهکاران سربار است
        {"gl": "7120", "dl": "500003", "kind": 1, "amount": 30},
        {"gl": "7110", "dl": "501001", "kind": 2, "amount": 40},    # حقوق دفتر: سرشکن و سربار
        {"gl": "7120", "dl": "520005", "kind": 1, "amount": 5},     # مرکز خدماتی
    ]
    labour, overhead, by_gl = service._conversion_pools(rows)
    assert labour == 100
    assert overhead == 95
    assert by_gl == {"7110": 140, "7190": 20, "7120": 35}


def test_comparison_period_uses_same_base_as_row():
    current = _report().finish()
    other = service.Report(["A", "B"])
    other.add("Gross Sales (Mrials)", {"A": 2000.0}, canon="gross")
    other.add("Discounts", {"A": 200.0}, canon="discount", ratio_base="gross")
    other.add("Total Net Sales", {"A": 1600.0}, kind="total", canon="net")
    other.add("سربار تولید", {"A": 100.0}, group="cogs_std")
    other.add("cost of goods sold", {"A": 800.0}, canon="cogs")

    service._attach_period(current, "p1", other.finish())
    rows = _by_label(current)

    assert rows["Discounts"]["periods"]["p1"]["ratio"] == 200 / 2000
    assert rows["سربار تولید"]["periods"]["p1"]["ratio"] == 100 / 1600
    assert rows["cost of goods sold"]["periods"]["p1"]["ratio"] == 800 / 1600

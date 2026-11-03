from app.services.bank_reconciliation_service import parse_bank_statement


def test_mellat_html_export_is_parsed_without_header_row_input():
    html = '''<!doctype html><html><body><table>
    <tr><td>بانک ملت ، تجربه ای متمایز</td></tr>
    <tr><td>شماره حساب :</td><td>9004173558 جاري متمرکز</td></tr>
    <tr><td>مانده</td><td>مبلغ گردش بستانکار</td><td>مبلغ گردش بدهکار</td><td>شرح</td><td>واریز کننده/ ذیتفع</td><td>شماره سریال</td><td>شناسه واریز</td><td>کد حسابگری</td><td>شعبه</td><td>زمان</td><td>تاریخ</td><td>رديف</td></tr>
    <tr><td>3,206,826,972</td><td>387,418,000</td><td>0</td><td>واریز انتقالی</td><td>کادوس</td><td>1</td><td>0</td><td>65136</td><td>وحید دستگردی</td><td>08:20:01</td><td>1405/01/05</td><td>1</td></tr>
    <tr><td>1,643,213,972</td><td>0</td><td>6,960,500,000</td><td>وصول چک چکاوک</td><td></td><td>73439038</td><td>0</td><td>150312</td><td>ستاد مرکزی چکاوک</td><td>08:38:19</td><td>1405/01/17</td><td>2</td></tr>
    </table></body></html>'''.encode('utf-8')
    rows, meta = parse_bank_statement(content=html, filename='mellat.html')
    assert len(rows) == 2
    assert meta['statement_bank_name'] == 'ملت'
    assert meta['statement_account_number'] == '9004173558'
    assert rows[0]['direction'] == 'deposit'
    assert rows[0]['amount'] == 387_418_000
    assert rows[0]['payer'] == 'کادوس'
    assert rows[1]['direction'] == 'withdrawal'
    assert rows[1]['amount'] == 6_960_500_000


def test_reconciliation_accepts_pdf_extension_before_parsing(monkeypatch):
    from app.services import bank_reconciliation_service as service
    expected = [["تاریخ", "واریز", "برداشت"], ["1405/01/01", "1", "0"]]
    monkeypatch.setattr(service, '_read_pdf_statement', lambda _content: expected)
    rows, _meta = service.parse_bank_statement(content=b'%PDF-fake', filename='mellat.pdf')
    assert len(rows) == 1
    assert rows[0]['direction'] == 'deposit'

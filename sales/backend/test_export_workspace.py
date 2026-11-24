import json
import unittest
import warnings
from unittest.mock import patch

import pandas as pd
from export_workspace import report


def snapshot():
    customers = pd.DataFrame([
        dict(code='1', label='customer A', short='A', name='account A', country='Iraq', account='A', source='test'),
        dict(code='2', label='customer B', short='B', name='account B', country='Oman', account='B', source='test'),
        dict(code='3', label='dormant', short='C', name='account C', country='Iraq', account='C', source='test'),
    ])
    values = [
        ('1405/08/01', 'S', '1', 'p1', 'رنگ مو', 10, 100, 90, 5, 5, 0, 0, 0),
        ('1405/08/02', 'S', '2', 'p2', 'استند', 2, 20, 0, 0, 20, 0, 0, 0),
        ('1405/08/03', 'Q', '1', 'p1', 'رنگ مو', 0, 0, 0, 0, 0, 0, 200, 20),
        ('1404/08/01', 'S', '1', 'p1', 'رنگ مو', 5, 50, 45, 0, 0, 0, 0, 0),
        ('1404/08/25', 'S', '1', 'p1', 'رنگ مو', 99, 990, 990, 0, 0, 0, 0, 0),
        ('1403/08/01', 'S', '1', 'p1', 'رنگ مو', 4, 40, 36, 0, 0, 0, 0, 0),
    ]
    lines = pd.DataFrame(values, columns=['date','kind','code','product_code','cat2','qty','gross','net','cash','mgmt','tax','req','req_pcs'])
    lines['cat1'] = lines.cat2
    lines['product'] = lines.product_code
    lines['brand'] = lines.code.map({'1':'A', '2':'B'})
    lines['country'] = lines.code.map({'1':'Iraq', '2':'Oman'})
    lines['year'] = lines.date.str[:4]
    lines['mm'] = lines.date.str[5:7]
    lines['month'] = lines.date.str[:7]
    lines['inv'] = lines.index.astype(str)
    return dict(lines=lines, customers=customers, today='1405/08/20')


class ExportWorkspaceTest(unittest.TestCase):
    def test_date_range_matches_only_selected_days_and_comparison(self):
        data = report(snapshot(), {'date_from': '1405/08/01', 'date_to': '1405/08/01'})
        self.assertEqual(data['kpis']['net'], 90)
        self.assertEqual(data['kpis']['net_comparison'], 45)
        self.assertEqual(data['quality']['kpis']['discount'], 10)
        empty = report(snapshot(), {'date_from': '1405/07/01', 'date_to': '1405/07/02'})
        self.assertEqual(empty['kpis']['net'], 0)
        snap = snapshot()
        extra = snap['lines'].iloc[[0]].copy()
        extra[['date', 'year', 'mm', 'month', 'net']] = ['1404/12/01', '1404', '12', '1404/12', 40]
        snap['lines'] = pd.concat([snap['lines'], extra], ignore_index=True)
        across_years = report(snap, {'date_from': '1404/12/01', 'date_to': '1405/08/01'})
        self.assertEqual(across_years['kpis']['net'], 130)
        self.assertEqual(across_years['kpis']['net_comparison'], 45)

    def test_tax_adjusted_rates_and_commercial_free_goods(self):
        snap = snapshot()
        # Tax is an addition, not a reduction in the discount amount.
        snap['lines'].loc[0, ['net', 'tax']] = [99, 9]
        # A free commercial product remains in quality analysis, unlike a stand.
        free = snap['lines'].iloc[[0]].copy()
        free[['gross', 'net', 'cash', 'mgmt', 'tax']] = [20, 0, 0, 0, 0]
        snap['lines'] = pd.concat([snap['lines'], free], ignore_index=True)
        data = report(snap, {})
        k = data['quality']['kpis']
        self.assertAlmostEqual(data['kpis']['disc_rate'], 50 / 140)
        self.assertEqual(k['discount'], 30)
        self.assertEqual(k['other_disc'], 20)
        self.assertAlmostEqual(k['disc_rate'], 30 / 120)
        self.assertAlmostEqual(k['disc_rate'], k['cash_rate'] + k['mgmt_rate'] + k['other_rate'])
        for dim in ('countries', 'customers', 'brands', 'categories'):
            self.assertEqual(sum(r['discount'] for r in data['quality'][dim]), 30)
        empty = report(snap, {'cat': ['missing']})['quality']['kpis']
        self.assertIsNone(empty['disc_rate'])

    def setUp(self):
        self.warning_context = warnings.catch_warnings()
        self.warning_context.__enter__()
        warnings.filterwarnings('ignore', message="The 'lsuffix' and 'rsuffix' keywords.*")
        self.addCleanup(self.warning_context.__exit__, None, None, None)

    def test_summary_and_all_tables_compare_same_period(self):
        data = report(snapshot(), {})
        self.assertEqual(data['kpis']['net'], 90)
        self.assertEqual(data['kpis']['pcs'], 12)
        self.assertEqual(data['kpis']['zero_amount_qty'], 2)
        self.assertEqual(data['kpis']['req'], 200)
        self.assertEqual(data['kpis']['net_comparison'], 45)
        for dimension in ('countries', 'customers', 'brands', 'categories'):
            self.assertEqual(sum(r['net'] for r in data[dimension]), 90)
            self.assertEqual(sum(r['net_ly'] for r in data[dimension]), 45)
        self.assertEqual(data['goods']['total']['net'], 90)
        self.assertEqual(data['goods']['total']['ly_net'], 45)
        self.assertEqual(data['trend'][7]['net_ly'], 45)
        json.dumps(data, allow_nan=False)

    def test_quality_excludes_promotional_lines_without_changing_sales(self):
        data = report(snapshot(), {})
        k = data['quality']['kpis']
        self.assertEqual(k['gross'], 100)
        self.assertEqual(k['mgmt'], 5)
        self.assertEqual(k['cash'], 5)
        self.assertEqual(k['other_disc'], 0)
        self.assertEqual([r['key'] for r in data['quality']['categories']], ['رنگ مو'])
        self.assertEqual(data['kpis']['gross'], 120)

    def test_customer_roster_and_missing_comparison_are_not_zero_growth(self):
        data = report(snapshot(), {})
        rows = {r['key']: r for r in data['customers']}
        self.assertEqual(set(rows), {'1','2','3'})
        self.assertEqual(rows['3']['status'], 'بدون خرید در دوره')
        self.assertIsNone(rows['2']['growth'])

    def test_alternate_comparison_year_and_filters(self):
        data = report(snapshot(), {'country':['Iraq'], 'months':['08'], 'cat':['رنگ مو']}, '1403')
        self.assertEqual(data['compare_year'], '1403')
        self.assertEqual(data['kpis']['net_comparison'], 36)
        self.assertEqual(data['goods']['total']['ly_net'], 36)
        import rahkaran_export as EX
        customer = EX.customer(snapshot(), '1', {}, '1403')
        self.assertEqual(customer['ly'], '1403')
        self.assertEqual(customer['kpis']['net_ly_same'], 36)
        self.assertEqual([r['key'] for r in data['countries']], ['Iraq'])
        old_year = report(snapshot(), {'year':'1404'})
        self.assertEqual(old_year['kpis']['net'], 1035)

    def test_empty_month_and_empty_quality_are_json_safe(self):
        for filters in ({'months':['07']}, {'cat':['استند']}):
            data = report(snapshot(), filters)
            json.dumps(data, allow_nan=False)
            self.assertEqual(data['quality']['kpis']['gross'], 0)

    def test_api_payload_and_legacy_report_are_available(self):
        from fastapi.testclient import TestClient
        import app as api
        snap = {**snapshot(), 'fetched':1}
        client = TestClient(api.app)
        with patch.object(api, '_rk_export', return_value=snap), patch.object(api.RK_EXPORT, 'is_live', return_value=False), \
             patch.object(api.exir_auth, 'internal_key', return_value='export-preview-test'):
            headers = {'X-Exir-Internal-Key':'export-preview-test'}
            new = client.get('/api/rk_export/workspace?compare_year=1403', headers=headers)
            old = client.get('/api/rk_export', headers=headers)
        self.assertEqual(new.status_code, 200, new.text)
        self.assertEqual(old.status_code, 200, old.text)
        self.assertEqual(new.json()['compare_year'], '1403')
        self.assertEqual(new.json()['kpis']['net'], old.json()['kpis']['net'])


if __name__ == '__main__':
    unittest.main()

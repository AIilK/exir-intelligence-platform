import json
import unittest
from unittest.mock import patch

import pandas as pd
from b2b_workspace import report, quality_snapshot


def snapshot():
    customers = pd.DataFrame([
        dict(code='1', short='same person', name='same person A', brand='A', province='East', city='e'),
        dict(code='2', short='same person', name='same person B', brand='B', province='West', city='w'),
        dict(code='3', short='inactive', name='inactive', brand='A', province='East', city='e'),
    ])
    values = [
        ('S', '1', '1405/08/02', 'p1', 10, 1000, 950, 20, 30, 100),
        ('S', '1', '1405/08/02', 'p2', 5, 500, 450, 10, 20, 50),
        ('S', '2', '1405/08/03', 'p1', 4, 400, 360, 0, 0, 0),
        ('R', '1', '1405/08/04', 'p1', 2, 200, 180, 0, 0, 0),
        ('Q', '1', '1405/08/01', 'p1', 20, 2000, 1900, 0, 0, 0),
        ('S', '1', '1404/08/02', 'p1', 6, 600, 560, 0, 0, 0),
    ]
    lines = pd.DataFrame(values, columns=['kind', 'code', 'date', 'product_code', 'qty', 'gross', 'net', 'cash', 'mgmt', 'tax'])
    lines['month'] = lines.date.str[:7]
    lines['product'] = lines.product_code
    lines['cat2'] = lines.product_code.map({'p1': 'رنگ مو', 'p2': 'اکسیدان'})
    lines['inv'] = '1'
    lines = lines.merge(customers, on='code')
    return dict(lines=lines, customers=customers, today='1405/08/20')


class B2BWorkspaceTest(unittest.TestCase):
    def test_date_range_filters_sales_requests_and_returns(self):
        data = report(snapshot(), 'R:1405/08/01:1405/08/02')
        self.assertEqual(data['kpis']['net'], 1400)
        self.assertEqual(data['kpis']['returns'], 0)
        self.assertEqual(data['kpis']['req_gross'], 2000)
        self.assertEqual(sum(r['net'] for r in data['monthly']), 1400)

    def test_quality_excludes_noncommercial_groups_from_totals_and_all_dimensions(self):
        for category in ['استند', 'استند رومیزی', 'استند/تبلیغاتی', 'تستر کرم پودر', 'تستر رژ لب', 'تستر پنکک', 'تبلیغاتی', 'سایر', 'نامشخص']:
            with self.subTest(category=category):
                snap = snapshot()
                snap['lines'].loc[snap['lines'].product_code.eq('p1'), 'cat2'] = category
                filtered = quality_snapshot(snap)
                data = report(filtered, '1405/08')
                self.assertEqual(data['kpis']['net'], 450)
                self.assertEqual(data['kpis']['cash'], 10)
                self.assertEqual(data['kpis']['mgmt'], 20)
                self.assertEqual(data['kpis']['other_disc'], 70)
                self.assertEqual([r['key'] for r in data['categories']], ['اکسیدان'])
                for dim in ('brands', 'customers', 'provinces'):
                    self.assertEqual(sum(r['net'] for r in data[dim]), 450)
                self.assertEqual(report(snap, '1405/08')['kpis']['net'], 1760)

    def test_quality_uses_real_dashboard_category_when_old_category_is_unknown(self):
        snap = snapshot()
        snap['lines']['cat1'] = 'سایر'
        self.assertEqual(len(quality_snapshot(snap)['lines']), len(snap['lines']))

    def test_totals_and_tax_adjusted_discount(self):
        data = report(snapshot(), '1405/08')
        self.assertEqual(data['kpis']['net'], 1760)
        self.assertEqual(data['kpis']['returns'], 180)
        self.assertEqual(data['kpis']['req_gross'], 2000)
        self.assertEqual(data['kpis']['qty'], 19)
        self.assertEqual(data['kpis']['other_disc'], 210)
        self.assertEqual(data['kpis']['discount'], 290)
        self.assertAlmostEqual(data['kpis']['disc_rate'], 290 / 1900)
        self.assertAlmostEqual(data['kpis']['cash_rate'], 30 / 1900)
        self.assertAlmostEqual(data['kpis']['mgmt_rate'], 50 / 1900)
        self.assertAlmostEqual(data['kpis']['other_rate'], 210 / 1900)
        self.assertEqual(data['goods']['total']['net'], 1760)
        for key in ('provinces', 'customers', 'brands', 'categories'):
            self.assertEqual(sum(row['discount'] for row in data[key]), 290)
            for row in data[key]:
                if row['gross'] > 0:
                    self.assertAlmostEqual(row['disc_rate'], row['cash_rate'] + row['mgmt_rate'] + row['other_rate'])
            self.assertEqual(sum(row['net'] for row in data[key]), 1760)
            self.assertEqual(sum(row['returns'] for row in data[key]), 180)
            self.assertEqual(sum(row['req_gross'] for row in data[key]), 2000)
        # JSON contains no NaN, even for customers with no activity.
        json.dumps(data, allow_nan=False)

    def test_customer_codes_preserved_and_effective_invoice_count(self):
        data = report(snapshot(), '1405/08')
        customers = {row['key']: row for row in data['customers']}
        self.assertEqual(set(customers), {'1', '2', '3'})
        self.assertEqual(customers['1']['invoices'], 1)
        self.assertEqual(customers['1']['net_cash'], 1430)
        self.assertEqual(customers['3']['net'], 0)
        self.assertAlmostEqual(customers['1']['growth'], 1400/560-1)

    def test_filters_apply_to_every_report(self):
        data = report(snapshot(), '1405/08', province='West', customer='2')
        self.assertEqual(data['kpis']['net'], 360)
        self.assertEqual(data['kpis']['req_gross'], 0)
        self.assertEqual([r['key'] for r in data['customers']], ['2'])
        self.assertEqual([r['key'] for r in data['brands']], ['B'])
        self.assertTrue(all(r['province'] == 'West' for r in data['heat']))
        self.assertEqual(data['goods']['total']['qty'], 4)
        month = next(m for m in data['monthly'] if m['month'] == '1405/08')
        self.assertEqual(month['qty'], 4)
        self.assertEqual(month['ly_qty'], 0)

    def test_monthly_quantities_include_same_month_last_year(self):
        data = report(snapshot(), '1405/08')
        month = next(m for m in data['monthly'] if m['month'] == '1405/08')
        self.assertEqual(month['qty'], 19)
        self.assertEqual(month['ly_qty'], 6)

    def test_map_brand_breakdown_preserves_amounts_and_quantities(self):
        snap = snapshot()
        snap['lines']['province'] = 'East'
        snap['customers']['province'] = 'East'
        data = report(snap, '1405/08')
        province = data['provinces'][0]
        brands = {r['brand']: r for r in province['brands']}
        self.assertEqual(brands['A']['net'], 1400)
        self.assertEqual(brands['A']['qty'], 15)
        self.assertEqual(brands['B']['net'], 360)
        self.assertEqual(brands['B']['qty'], 4)
        self.assertEqual(sum(r['net'] for r in brands.values()), province['net'])
        self.assertEqual(sum(r['qty'] for r in brands.values()), province['qty'])

    def test_no_activity_and_request_only_periods(self):
        for period in ('1405/07', '1405/08/01'):
            with self.subTest(period=period):
                data = report(snapshot(), period)
                self.assertEqual(data['kpis']['net'], 0)
                self.assertIsNone(data['kpis']['disc_rate'])
                self.assertIsNone(data['kpis']['cash_rate'])
                json.dumps(data, allow_nan=False)
                self.assertEqual(data['kpis']['req_gross'], 2000 if period == '1405/08/01' else 0)

    def test_product_filter_snapshot_and_selected_day(self):
        snap = snapshot()
        snap['lines'] = snap['lines'][snap['lines'].product_code.eq('p2')]
        data = report(snap, '1405/08/02')
        self.assertEqual(data['kpis']['net'], 450)
        self.assertEqual(data['goods']['total']['qty'], 5)
        self.assertEqual(sum(r['net'] for r in data['daily']), 450)

    def test_api_payload_includes_metadata_and_product_filters(self):
        from fastapi.testclient import TestClient
        import app as api
        snap = {**snapshot(), 'fetched': 1, 'since': '1404/01/01'}
        # No lifespan: tests must not launch live SQL workers or write caches.
        client = TestClient(api.app)
        with patch.object(api, '_rk_sales', return_value=snap), patch.object(api.RK_SALES, 'is_live', return_value=False), \
             patch.object(api.exir_auth, 'internal_key', return_value='workspace-test-key'):
            response = client.get('/api/rk_sales/workspace?period=1405/08&product=p2&quality_only=1',
                                  headers={'X-Exir-Internal-Key': 'workspace-test-key'})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['kpis']['net'], 450)
        self.assertEqual(data['kpis']['discount'], 100)
        self.assertAlmostEqual(data['kpis']['disc_rate'], .2)
        self.assertAlmostEqual(data['categories'][0]['disc_rate'], .2)
        self.assertEqual(data['goods']['total']['qty'], 5)
        self.assertEqual(data['options']['brands'], ['A', 'B'])
        self.assertEqual(data['today'], '1405/08/20')
        self.assertFalse(data['live'])


if __name__ == '__main__':
    unittest.main()

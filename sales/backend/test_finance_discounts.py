import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from exir_auth import allowed
from finance_discounts import karamad_invoice_rates, karamad_registered_discounts, report


class FinanceDiscountsTest(unittest.TestCase):
    def test_karamad_totals_follow_invoice_amounts_and_exclude_returns(self):
        base = dict(date='1405/08/01', branch='هیبرید تهران', customer='A', product_code='1',
                    product='کالا', qty=1, is_return=False, cash_disc=0, mgmt_disc=0)
        lines = pd.DataFrame([
            dict(base, inv_no='7', inv_id='11', gross=100, disc=30, vol_disc=25, mgmt_disc=5),
            dict(base, inv_no='7', inv_id='11', gross=300, disc=30, vol_disc=20, cash_disc=10),
            dict(base, inv_no='8', inv_id='12', gross=100, disc=20, vol_disc=20),
            dict(base, inv_no='9', inv_id='13', gross=-100, disc=-30, vol_disc=-30, is_return=True),
            dict(base, inv_no='10', inv_id='14', gross=100, disc=50, vol_disc=50, date='1405/07/01'),
        ])
        args = (lines, 'karamad', '1405/08/02')
        summary = report(*args)
        self.assertEqual(summary['total']['discount_rate'], 80 / 500)
        group = summary['rows'][0]['group']
        docs = report(*args, group=group)['rows']
        doc = next(r for r in docs if r['invoice_id'] == '11')
        self.assertEqual(doc['discount_rate'], 60 / 400)
        items = report(*args, group=group, invoice_id='11')['rows']
        self.assertEqual(len(items), 2)
        self.assertEqual(sum(r['volume'] for r in items), doc['volume'])
        self.assertNotIn('mgmt_rate', items[0])

    def test_saved_policy_rates_are_returned_without_recalculation(self):
        connection = MagicMock()
        item = {'invoice_id': 5178, 'line_no': 1, 'product_code': '123', 'product': 'کالا', 'qty': 36,
                'cash_amount': 0, 'cash_pct': 0, 'has_policy': 5178, 'is_cash': False}
        source_rows = pd.DataFrame([
            dict(item, policy='تخفیف مدیریتی', registered_pct=5),
            dict(item, policy='تخفیف جشنواره', registered_pct=5),
            dict(item, policy='تخفیف جشنواره', registered_pct=15),
            dict(item, policy='سیاست نقدی', registered_pct=22, is_cash=True),
            dict(item, line_no=2, policy='تخفیف مدیریتی', registered_pct=None),
            dict(item, line_no=3, has_policy=None, policy=None, registered_pct=None),
        ])
        with patch('finance_discounts.sql_source.read_env', return_value={}), \
             patch('finance_discounts.sql_source.settings', return_value={}), \
             patch('finance_discounts.sql_source.connect', return_value=connection), \
             patch('finance_discounts.sql_source._read', return_value=source_rows) as read:
            rows = karamad_registered_discounts(None, 5178)
        sql = read.call_args.args[1]
        self.assertIn('d.Per AS registered_pct', sql)
        self.assertIn('v.CashPercent AS cash_pct', sql)
        self.assertEqual(read.call_args.args[2], [5178])
        self.assertEqual([row['line_no'] for row in rows], [1, 2, 3])
        self.assertEqual([entry['pct'] for entry in rows[0]['mgmt']], [5])
        self.assertEqual([entry['pct'] for entry in rows[0]['volume']], [5, 15])
        self.assertEqual([entry['pct'] for entry in rows[0]['cash']], [22])
        self.assertIsNone(rows[1]['mgmt'][0]['pct'])
        self.assertEqual(rows[2]['mgmt'], [])
        connection.close.assert_called_once()

    def test_invoice_rates_preserve_distinct_saved_rates(self):
        items = [
            {'mgmt': [{'pct': 5}], 'cash': [], 'volume': [{'pct': 5}, {'pct': 15}]},
            {'mgmt': [{'pct': 5}, {'pct': None}], 'cash': [{'pct': 20}], 'volume': [{'pct': 15}]},
        ]
        with patch('finance_discounts._karamad_registered_by_invoice', return_value={5178: items}):
            result = karamad_invoice_rates(None, [5178])['5178']
        self.assertEqual(result, {'mgmt': [{'pct': 5}, {'pct': None}],
                                  'cash': [{'pct': 20}], 'volume': [{'pct': 5}, {'pct': 15}]})

    def test_rahkaran_uses_registered_deductions_and_separate_volume(self):
        lines = pd.DataFrame([
            dict(kind='S', date='1405/08/01', province='تهران', country='عراق', short='A',
                 inv='7', invoice_id=11, gross=100, net=72, tax=7, discount=35,
                 cash=5, mgmt=10, volume=8),
        ])
        total = report(lines, 'b2b', '1405/08/02')['total']
        self.assertEqual(total['discount_rate'], .35)
        self.assertEqual(total['volume_rate'], .08)
        self.assertEqual(total['other_rate'], .12)
        export = report(lines, 'export', '1405/08/02')['total']
        self.assertEqual(export['discount_rate'], .35)
        self.assertEqual(export['cash_rate'], 0)

    def test_permission_is_specific_to_finance_discounts(self):
        path = '/api/finance-discounts'
        self.assertTrue(allowed({'modules': ['discounts']}, path, 'GET'))
        self.assertFalse(allowed({'modules': ['sales']}, path, 'GET'))

    def test_rahkaran_defaults_to_last_active_month_only_without_an_explicit_range(self):
        lines = pd.DataFrame([
            dict(kind='S', date='1405/08/30', province='تهران', short='A', inv='7', invoice_id=11,
                 gross=100, discount=20, cash=0, mgmt=0, volume=0),
            dict(kind='Q', date='1405/09/01', province='تهران', short='A', inv='8', invoice_id=12,
                 gross=100, discount=0, cash=0, mgmt=0, volume=0),
        ])
        data = report(lines, 'b2b', '1405/09/03')
        self.assertEqual(data['period'], {'from': '1405/08/01', 'to': '1405/08/30', 'latest_month': True})
        self.assertEqual(data['total']['discount_rate'], .2)
        self.assertEqual(report(lines, 'b2b', '1405/09/03', group='تهران')['rows'][0]['invoice'], '7')
        self.assertEqual(report(lines, 'b2b', '1405/09/03', '1405/09/01', '1405/09/03')['rows'], [])

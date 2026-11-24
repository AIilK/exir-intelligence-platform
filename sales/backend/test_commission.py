import unittest
import pandas as pd

import commission as K


def member(branch, supervisor, gross=50000, net=45000):
    return dict(branch=branch, supervisor=supervisor, gross=gross*K.M,
                net=net*K.M, net_cash=(net+100)*K.M, base=net*K.M,
                base_forecast=net*2*K.M, gross_forecast=gross*2*K.M,
                target_rial=None, ret_sale=0, ret_dist=0)


class SupervisorTargetsTest(unittest.TestCase):
    def calculate(self, branch, names, rows, month='1405/08'):
        plan = {'supervisors': [{'branch': branch, 'name': n} for n in names]}
        return K._supervisors(plan, rows, K.rules_for(month))

    def test_regular_branch_uses_instruction_targets_per_supervisor(self):
        branch = 'هیبرید اصفهان'
        result = self.calculate(branch, ['a', 'b'], [member(branch, 'a', gross=120000, net=110000)])
        for r in result:
            self.assertEqual(r['supervisor_count'], 2)
            self.assertEqual(r['t1'], 100000*K.M)
            self.assertEqual(r['t2'], 200000*K.M)
        r = result[0]
        self.assertAlmostEqual(r['commission'], 850*K.M)
        self.assertAlmostEqual(r['payable'], 850*K.M*.85)
        self.assertAlmostEqual(r['forecast_commission'], 2050*K.M)
        self.assertEqual(result[1]['commission'], 0)

    def test_tehran_teams_ignore_registered_targets(self):
        branch = 'هیبرید تهران'
        east, west, manager = 'حبیب موسوی - تهران شرق', 'شهرام محمودی - تهران غرب', 'امیر شایان'
        team = [dict(member(branch, east, gross=220000), target_rial=215000*K.M),
                dict(member(branch, west, gross=310000), target_rial=275000*K.M)]
        plan = {'branch_targets': {branch: {'rial': 520000*K.M}},
                'supervisors': [{'branch': branch, 'name': n} for n in (east, west, manager)]}
        rows = {r['name']: r for r in K._supervisors(plan, team, K.rules_for('1405/08'))}
        self.assertEqual(rows[east]['t1'], 120000*K.M)
        self.assertEqual(rows[west]['t1'], 120000*K.M)
        self.assertEqual(rows[manager]['t1'], 120000*K.M)
        self.assertAlmostEqual(rows[manager]['t2'], 250000*K.M, places=3)
        self.assertEqual(rows[manager]['gross'], 530000*K.M)
        self.assertEqual(rows[manager]['base'], 90000*K.M)
        self.assertEqual(rows[manager]['commission'], 675*K.M)
        self.assertEqual(rows[manager]['visitors'], 2)
        plan['branch_targets'] = {}
        rows = K._supervisors(plan, team, K.rules_for('1405/08'))
        self.assertEqual(rows[2]['commission'], 675*K.M)
        self.assertEqual(rows[2]['t1'], 120000*K.M)

    def test_unique_supervisors_from_roster_and_team_normalized_branch(self):
        result = self.calculate('هیبرید مازندران', ['a', 'a'],
                                [member('هیبریدی مازندران', 'a'), member('هیبرید مازندران', 'b')])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(r['supervisor_count'] == 2 and r['t1'] == 20000*K.M for r in result))

    def test_tehran_manager_uses_all_branch_sales_including_unlisted_visitors(self):
        branch = 'هیبرید تهران'
        east, west, manager = 'حبیب موسوی - تهران شرق', 'شهرام محمودی - تهران غرب', 'امیر شایان'
        team = [member(branch, east, gross=130000, net=100000), member(branch, west, gross=60000, net=50000)]
        raw = pd.DataFrame([
            dict(branch=branch, gross=g*K.M, net=n*K.M, cash_disc=c*K.M, is_return=g < 0, dist_return=False)
            for g, n, c in [(130000, 100000, 100), (60000, 50000, 100), (40000, 30000, 100), (-10000, -8000, -50)]
        ] + [dict(branch='هیبرید اصفهان', gross=999999*K.M, net=999999*K.M, cash_disc=0,
                  is_return=False, dist_return=False)])
        plan = {'supervisors': [{'branch': branch, 'name': name} for name in (east, west, manager)]}
        rows = {r['name']: r for r in K._supervisors(plan, team, K.rules_for('1405/08'), raw, 2)}
        self.assertEqual(rows[east]['gross'], 130000*K.M)
        self.assertEqual(rows[west]['gross'], 60000*K.M)
        shayan = rows[manager]
        self.assertEqual(shayan['sales_scope'], 'branch')
        self.assertEqual(shayan['gross'], 220000*K.M)
        self.assertEqual(shayan['base'], 172250*K.M)
        self.assertEqual(shayan['forecast'], 344500*K.M)
        self.assertEqual(shayan['ach'], 220000/120000)
        self.assertAlmostEqual(shayan['commission'], (120000*.0075 + 52250*.01)*K.M)
        self.assertEqual(shayan['ret_sale'], 8000*K.M)

    def test_isfahan_two_and_single_supervisor(self):
        for names, divisor in [(['a', 'b'], 2), (['a'], 1)]:
            with self.subTest(names=names):
                r = self.calculate('هیبرید اصفهان', names, [])[0]
                self.assertEqual(r['t1'], 100000*K.M)
                self.assertEqual(r['t2'], 200000*K.M)

    def test_mehr_unchanged(self):
        r = self.calculate('هیبرید تهران', ['a', 'b', 'c'], [], '1405/07')[0]
        self.assertEqual(r['t1'], 200000*K.M)
        self.assertEqual(r['t2'], 400000*K.M)

    def test_alborz_has_no_supervisor_rule(self):
        r = self.calculate('هیبرید البرز', ['a'], [])[0]
        self.assertIsNone(r['t1'])
        self.assertIsNone(r['commission'])

    def test_gross_qualification_net_commission_and_boundary(self):
        branch = 'هیبرید اصفهان'
        rows = [member(branch, 'a', gross=100000, net=30000)]
        r = self.calculate(branch, ['a', 'b'], rows)[0]
        self.assertEqual(r['ach_t1'], 1)
        self.assertEqual(r['commission'], 30000*K.M*.0075)
        rows[0]['gross'] -= 1
        self.assertEqual(self.calculate(branch, ['a', 'b'], rows)[0]['commission'], 0)


class KhorasanVisitorTiersTest(unittest.TestCase):
    def test_aban_first_tier_extends_to_two_billion_toman(self):
        rules = K.rules_payload('1405/08')
        tiers = rules['rulesets']['هیبرید خراسان']['visitor']
        self.assertEqual(tiers, [[20000, .03], [40000, .05], [60000, .06], [80000, .07], [None, .09]])
        for volume, expected in [
            (10000*K.M, (1, .03)),
            (15000*K.M, (1, .03)),
            (20000*K.M - 1, (1, .03)),
            (20000*K.M, (2, .05)),
            (40000*K.M - 1, (2, .05)),
            (40000*K.M, (3, .06)),
        ]:
            with self.subTest(volume=volume):
                self.assertEqual(K.visitor_rate(volume, tiers), expected)

    def test_mehr_khorasan_and_aban_alborz_unchanged(self):
        mehr = K.rules_for('1405/07')
        tiers = mehr['rulesets'][K.ruleset_of('هیبرید خراسان', mehr)]['visitor']
        self.assertEqual(K.visitor_rate(15000*K.M, tiers), (3, .06))
        alborz = K.rules_for('1405/08')['rulesets']['هیبرید البرز']['visitor']
        self.assertEqual(alborz[0], [10000, .03])


class AbanSpecialInvoicesTest(unittest.TestCase):
    def calculate(self, kind, gross_values, mgmt_values):
        visitor = dict(id='v', branch='هیبرید تهران', supervisor='', code='v', name='v', type=kind)
        lines = [dict(seller_key='v', seller='v', seller_code='v', branch=visitor['branch'],
                      date='1405/08/10', gross=g*K.M, net=(g-m-100)*K.M,
                      cash_disc=100*K.M, mgmt_disc=m*K.M, qty=1, is_return=False,
                      inv_id=str(i), inv_no=str(i), customer='customer', customer_code='1',
                      payable=(g-m-100)*K.M, vat=0, category='سایر', brand='سایر',
                      product='سایر', dist_return=False)
                 for i, (g, m) in enumerate(zip(gross_values, mgmt_values))]
        plan = dict(visitors=[visitor], targets={'v': {'rial': sum(gross_values)*K.M}})
        return K.compute(plan, pd.DataFrame(lines), None, '1405/08', 26, 26, None)['visitors'][0]

    def test_management_threshold_and_details_for_both_visitor_types(self):
        for kind in ('commission', 'employed'):
            for discount, qualifies in ((199, False), (200, False), (201, True)):
                with self.subTest(kind=kind, discount=discount):
                    row = self.calculate(kind, [5000]*4, [discount, 0, 0, 0])
                    self.assertEqual(row['special_n'], int(qualifies))
                    self.assertEqual(len(row['special_invoice_details']), 1)
                    self.assertEqual(row['special_invoice_details'][0]['base_rate_applies'], qualifies)
                    special_base = (5000-discount)*K.M if qualifies else 0
                    self.assertEqual(row['special_base'], special_base)
                    base_rate = .03 if kind == 'commission' else .02
                    expected = (row['base']-special_base)*row['rate'] + special_base*base_rate
                    self.assertAlmostEqual(row['commission'], expected)

    def test_wholesale_and_management_union_has_no_double_count(self):
        for kind in ('commission', 'employed'):
            with self.subTest(kind=kind):
                row = self.calculate(kind, [8000, 4000, 4000, 4000], [200, 100, 0, 0])
                self.assertEqual(row['special_n'], 2)
                self.assertTrue(row['special_ws_on'])
                self.assertTrue(row['special_mg_on'])
                self.assertEqual(row['special_base'], 11700*K.M)
                self.assertEqual(len(row['special_invoices']), 2)
                self.assertTrue(row['special_invoices'][0]['wholesale'])
                self.assertTrue(row['special_invoices'][0]['mgmt_inv'])
                base_rate = .03 if kind == 'commission' else .02
                self.assertAlmostEqual(row['commission'], (row['base']-11700*K.M)*row['rate'] + 11700*K.M*base_rate)

    def test_wholesale_below_share_threshold_is_still_visible(self):
        row = self.calculate('commission', [8000]+[4000]*8, [0]*9)
        self.assertEqual(row['special_n'], 0)
        self.assertEqual(len(row['special_invoice_details']), 1)
        self.assertFalse(row['special_invoice_details'][0]['base_rate_applies'])

    def test_no_special_invoices_has_empty_details(self):
        row = self.calculate('commission', [5000]*4, [0]*4)
        self.assertEqual(row['special_invoice_details'], [])
        self.assertEqual(row['special_n'], 0)

    def test_wholesale_requires_more_than_twenty_one_percent_in_aban(self):
        for gross, expected in ((8400, False), (8401, True)):
            with self.subTest(gross=gross):
                # مجموع فروش ۴۰٬۰۰۰ میلیون ریال؛ مرز دقیق عمده ۸٬۴۰۰ است.
                rest = (40000-gross)/8
                row = self.calculate('commission', [gross]+[rest]*8, [0]*9)
                self.assertEqual(row['special_ws_on'], expected)
                self.assertEqual(row['special_n'], int(expected))


class AbanBaseTest(unittest.TestCase):
    def test_compute_cash_base_reserves_and_effective_rate(self):
        visitors = [dict(id=t, branch='هیبرید آذربایجان شرقی', supervisor='',
                         code=t, name=t, type=t) for t in ('commission', 'employed')]
        lines = []
        for v in visitors:
            for i in range(2):
                lines.append(dict(seller_key=v['id'], seller=v['name'], seller_code=v['code'],
                    branch=v['branch'], date='1405/08/10', gross=4000*K.M, net=3600*K.M,
                    cash_disc=400*K.M, mgmt_disc=0, qty=1, is_return=False,
                    inv_id=f"{v['id']}-{i}", inv_no=str(i), customer='customer', customer_code='1',
                    payable=3600*K.M, vat=0, category='سایر', brand='سایر', product='سایر', dist_return=False))
        plan = dict(visitors=visitors, targets={'employed': {'rial': 8000*K.M}})
        result = K.compute(plan, pd.DataFrame(lines), None, '1405/08', 26, 26, None)
        comm, emp = result['visitors']
        self.assertEqual(comm['special_n'], 0)
        self.assertEqual(comm['rate'], .05)
        self.assertEqual(comm['base'], comm['net_cash'])
        self.assertAlmostEqual(comm['commission']/comm['net_cash'], .05)
        self.assertAlmostEqual(comm['reserve'], comm['commission']*.15)
        self.assertAlmostEqual(emp['commission'], emp['net_cash']*.03)
        self.assertAlmostEqual(emp['reserve'], emp['commission']*.10)
        self.assertAlmostEqual(emp['payable'], emp['commission']*.90)


if __name__ == '__main__':
    unittest.main()

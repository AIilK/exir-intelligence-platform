import unittest
import pandas as pd
import rahkaran_export as EX
import rahkaran_sales as RS


def snapshot():
    rows = []
    for year in ('1404', '1405'):
        for code, category, net, qty in [('1209902001', 'کاتالوگ', 10, 2), ('1209908005', 'استند ایستاده', 30, 3)]:
            rows.append(dict(year=year, mm='08', month=f'{year}/08', date=f'{year}/08/01', kind='S',
                             code='1', brand='آرکیا', country='عراق', product_code=code, product=category,
                             cat1='POSM', cat2=category, net=net, gross=net, qty=qty,
                             req=0, req_pcs=0, inv=code, tax=0))
    return dict(today='1405/08/20', lines=pd.DataFrame(rows), customers=pd.DataFrame([
        dict(code='1', label='مشتری', short='مشتری', name='مشتری', country='عراق', account='آرکیا', source='test')]))


class ExportCategoriesTest(unittest.TestCase):
    def test_filter_chart_and_goods_tree_use_the_same_category(self):
        snap = snapshot()
        data = EX.report(snap, {})
        self.assertEqual(set(data['options']['cat']), {'کاتالوگ', 'استند ایستاده'})
        self.assertNotIn('POSM', data['categories']['key'].tolist())
        self.assertEqual(set(data['categories']['key']), set(data['sku']['cat2']))
        self.assertEqual(data['kpis']['net'], 40)
        self.assertEqual(data['kpis']['pcs'], 5)
        for category, amount, quantity in [('کاتالوگ', 10, 2), ('استند ایستاده', 30, 3)]:
            with self.subTest(category=category):
                filters = {'cat': [category]}
                report = EX.report(snap, filters)
                tree = EX.goods_tree(snap, filters)
                customer = EX.customer(snap, '1', filters)
                self.assertEqual(report['kpis']['net'], amount)
                self.assertEqual(report['kpis']['pcs'], quantity)
                self.assertEqual(tree['total']['net'], amount)
                self.assertEqual(customer['kpis']['net'], amount)
                self.assertEqual(set(report['sku']['cat2']), {category})
                self.assertEqual(set(customer['products']['cat2']), {category})

    def test_category_names_come_from_existing_shared_mapping(self):
        categories = RS.product_categories(pd.Series(['1209902001', '1209908005']))
        self.assertEqual(categories['cat2'].tolist(), ['کاتالوگ', 'استند ایستاده'])


if __name__ == '__main__':
    unittest.main()

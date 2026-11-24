"""گزارش‌های پنج صفحه جدید B2B؛ همه محاسبات از snapshot فقط‌خواندنی راهکاران."""
from __future__ import annotations

import pandas as pd
import analytics as A
import rahkaran_sales as RS


def quality_snapshot(snap: dict) -> dict:
    """تحلیل تخفیف فقط برای کالای تجاری؛ snapshot اصلی و گزارش‌های فروش دست‌نخورده‌اند."""
    lines = snap['lines']
    excluded = pd.Series(False, index=lines.index)
    for column in ('cat1', 'cat2'):
        if column not in lines:
            continue
        category = lines[column].map(RS.norm).str.lower()
        excluded |= category.str.contains('استند|تستر|تبلیغاتی|نمونه|tester|stand', regex=True)
        if column == 'cat2':
            excluded |= category.isin(['', 'سایر', 'نامشخص', 'بدون گروه', 'بدون دسته بندی'])
    return {**snap, 'lines': lines[~excluded]}


def report(snap: dict, period: str, brand: str | None = None,
           province: str | None = None, customer: str | None = None) -> dict:
    s, r, ly, keep, period = RS._scope(snap, period, brand, province, customer)
    current, _, _ = RS.window(snap, period)
    requests = snap['lines'][current & keep & snap['lines']['kind'].eq('Q')]
    cust = snap['customers']
    for col, selected in [('brand', brand), ('province', province), ('code', customer)]:
        if selected:
            cust = cust[cust[col].map(RS.norm).eq(RS.norm(selected))]

    def aggregate(dim: str, include_roster: bool = False) -> list[dict]:
        def sums(df, fields):
            return df.groupby(dim)[list(fields)].sum().rename(columns=fields)
        g = sums(s, {'net': 'net', 'gross': 'gross', 'qty': 'qty', 'cash': 'cash', 'mgmt': 'mgmt', 'tax': 'tax'})
        g = g.join(sums(ly, {'net': 'ly_net'}), how='outer')
        g = g.join(sums(r, {'net': 'returns', 'qty': 'ret_qty'}), how='outer')
        g = g.join(sums(requests, {'gross': 'req_gross', 'qty': 'req_qty'}), how='outer')
        g = g.join(s.drop_duplicates(['code', 'date']).groupby(dim).size().rename('invoices'), how='outer')
        g = g.join(s.groupby(dim)['code'].nunique().rename('customers'), how='outer')
        if include_roster:
            g = g.reindex(g.index.union(cust['code']))
        g = g.fillna(0)
        g['net_cash'] = g.net + g.cash
        g['discount'] = g.gross + g.tax - g.net
        g['other_disc'] = g.discount - g.cash - g.mgmt
        gross = g.gross.where(g.gross > 0)
        for rate, amount in [('disc_rate', 'discount'), ('cash_rate', 'cash'),
                             ('mgmt_rate', 'mgmt'), ('other_rate', 'other_disc')]:
            g[rate] = g[amount] / gross
        g['return_rate'] = g.returns / g.net.where(g.net > 0)
        g['growth'] = g.net / g.ly_net.where(g.ly_net > 0) - 1
        g['share'] = g.net / float(s.net.sum()) if s.net.sum() else None
        g['avg_invoice'] = g.net / g.invoices.where(g.invoices > 0)
        g = g.reset_index().rename(columns={dim: 'key'})
        g['label'] = g['key']
        if dim == 'code':
            info = snap['customers'].drop_duplicates('code').set_index('code')
            for col in ['short', 'name', 'province', 'brand', 'city']:
                g[col] = g['key'].map(info[col])
            g['label'] = g['short'].fillna(g['key'])
            g['last_date'] = g['key'].map(snap['lines'][snap['lines']['kind'].eq('S')].groupby('code')['date'].max())
        return A.records(g.sort_values('net', ascending=False))

    def heat(df: pd.DataFrame, metric: str) -> list[dict]:
        return A.records(df.groupby(['province', 'date']).agg(net=(metric, 'sum'), qty=('qty', 'sum')).reset_index())

    daily = s.groupby('date').agg(net=('net', 'sum'), qty=('qty', 'sum'))
    daily = daily.join(requests.groupby('date')['gross'].sum().rename('req_gross'), how='outer')
    daily = daily.join(r.groupby('date')['net'].sum().rename('returns'), how='outer').fillna(0)
    kpis = RS._kpis(s, r, ly, cust['code'], RS._ytd(snap, keep), requests)
    kpis.update(mgmt=float(s.mgmt.sum()), tax=float(s.tax.sum()),
                other_disc=float((s.gross + s.tax - s.net - s.cash - s.mgmt).sum()))
    # NetPrice راهکاران شامل مالیات است؛ نرخ قدیمی _kpis (۱ − خالص/ناخالص)
    # برای تحلیل تخفیف معتبر نیست. همه کارت‌ها و نمودارها از همین مبنا استفاده می‌کنند.
    kpis['discount'] = kpis['gross'] + kpis['tax'] - kpis['net']
    for rate, amount in [('disc_rate', 'discount'), ('cash_rate', 'cash'),
                         ('mgmt_rate', 'mgmt'), ('other_rate', 'other_disc')]:
        kpis[rate] = kpis[amount] / kpis['gross'] if kpis['gross'] > 0 else None
    monthly_keep = keep
    if period.startswith('R:'):
        _, comparison, _ = RS.window(snap, period)
        monthly_keep = keep & (current | comparison)
    monthly = RS._monthly(snap['lines'], monthly_keep, snap['today'])
    sales = snap['lines'][monthly_keep & snap['lines']['kind'].eq('S')]
    qty_by_month = sales.groupby('month')['qty'].sum()
    for row in monthly:
        month = row['month']
        row['qty'] = float(qty_by_month.get(month, 0))
        row['ly_qty'] = float(qty_by_month.get(f"{int(month[:4])-1}{month[4:]}", 0))
    provinces = aggregate('province')
    brand_mix = s.groupby(['province', 'brand'])[['net', 'qty']].sum()
    for row in provinces:
        row['brands'] = ([{'brand': brand_name, 'net': float(values.net), 'qty': float(values.qty)}
                          for brand_name, values in brand_mix.loc[row['key']].iterrows()]
                         if row['key'] in brand_mix.index.get_level_values('province') else [])
    return {'period': period, 'kpis': kpis, 'provinces': provinces,
            'customers': aggregate('code', True), 'brands': aggregate('brand'), 'categories': aggregate('cat2'),
            'daily': A.records(daily.reset_index()), 'heat': heat(s, 'net'), 'heat_req': heat(requests, 'gross'),
            'monthly': monthly,
            'goods': RS.build_tree(s, ly, r)}

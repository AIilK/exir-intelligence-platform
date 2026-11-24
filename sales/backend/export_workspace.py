"""نسخه مستقل صادرات؛ از همان snapshot و قواعد تبدیل ارز نسخه اصلی استفاده می‌کند."""
from __future__ import annotations

import pandas as pd
import analytics as A
import rahkaran_export as EX
import rahkaran_sales as RS


def date_scope(snap, filters, compare_year=None):
    lo, hi = filters['date_from'], filters['date_to']
    year = hi[:4]
    baseline = compare_year if compare_year and compare_year != year else str(int(year) - 1)
    delta = int(year) - int(baseline)
    shift = lambda d: f'{int(d[:4])-delta}{d[4:]}'
    lines = snap['lines']
    current = lines[lines.date.between(lo, hi)].assign(year=year)
    prior = lines[lines.date.between(shift(lo), shift(hi))].assign(year=baseline)
    scoped = {**snap, 'lines': pd.concat([current, prior]), 'today': hi}
    f = {**filters, 'year': year, 'months': [], '_range_scoped': True}
    f.pop('date_from'); f.pop('date_to')
    return scoped, f, baseline


def report(snap: dict, filters: dict, compare_year: str | None = None) -> dict:
    if filters.get('date_from') and filters.get('date_to'):
        scoped, f, baseline = date_scope(snap, filters, compare_year)
        result = report(scoped, f, baseline)
        result['today'] = snap['today']
        result['years'] = sorted(snap['lines'].year.unique().tolist(), reverse=True)
        result['date_range'] = {'from': filters['date_from'], 'to': filters['date_to']}
        return result
    base = EX.report(snap, filters)
    year, previous, cutoff = EX._years(snap, filters)
    years = base['years']
    baseline = compare_year if compare_year in years and compare_year != year else previous
    filtered = EX._filter(snap['lines'], filters)
    current = filtered[filtered.year.eq(year)]
    prior = filtered[filtered.year.eq(baseline)]
    if not filters.get('_range_scoped'):
        prior = prior[prior.date.str[5:].le(cutoff[5:])]
    sales = current[current.kind.eq('S')]
    previous_sales = prior[prior.kind.eq('S')]

    def groups(dim, cur=current, prev=prior):
        combined = pd.concat([cur, prev])
        frame = EX._two_years(combined, dim, year, baseline).set_index('key')
        if dim == 'code':
            codes = EX._scope_codes(snap, filters)
            frame = frame.reindex(frame.index.union(codes))
            for key in ('net', 'gross', 'pcs', 'req', 'req_pcs'):
                for suffix in ('', '_ly'):
                    frame[key + suffix] = frame[key + suffix].fillna(0)
            frame['growth'] = frame.net / frame.net_ly.where(frame.net_ly > 0) - 1
            frame['share'] = frame.net / frame.net.sum() if frame.net.sum() else None
        monetary = cur.groupby(dim)[['cash', 'mgmt', 'tax']].sum()
        frame = frame.join(monetary).fillna({'cash': 0, 'mgmt': 0, 'tax': 0})
        frame['discount'] = frame.gross + frame.tax - frame.net
        frame['other_disc'] = frame.discount - frame.cash - frame.mgmt
        for rate, amount in [('disc_rate', 'discount'), ('cash_rate', 'cash'),
                             ('mgmt_rate', 'mgmt'), ('other_rate', 'other_disc')]:
            frame[rate] = frame[amount] / frame.gross.where(frame.gross > 0)
        frame['qty_growth'] = frame.pcs / frame.pcs_ly.where(frame.pcs_ly > 0) - 1
        frame['label'] = frame.index
        bought = cur[cur.kind.eq('S') & cur.qty.gt(0)]
        frame['customers'] = frame.index.to_series().map(bought.groupby(dim).code.nunique()).fillna(0)
        invoices = cur[cur.kind.eq('S') & cur.net.ne(0)].drop_duplicates([dim, 'code', 'date'])
        frame['invoices'] = frame.index.to_series().map(invoices.groupby(dim).size()).fillna(0)
        if dim == 'code':
            info = snap['customers'].drop_duplicates('code').set_index('code')
            for col in ('label', 'name', 'country'):
                frame[col] = frame.index.to_series().map(info[col])
            history = snap['lines'][snap['lines'].kind.eq('S') & snap['lines'].date.le(f'{year}/{cutoff[5:]}')]
            frame['last_date'] = frame.index.to_series().map(history.groupby('code').date.max())
            frame['status'] = frame.pcs.map(lambda qty: 'دارای خرید در دوره' if qty > 0 else 'بدون خرید در دوره')
        return A.records(frame.reset_index().rename(columns={'index': 'key'}).sort_values('net', ascending=False))

    # فقط در تحلیل تخفیف اقلام تبلیغاتی/تستر و گروه‌های ناشناخته کنار می‌روند.
    category = sales.cat2.map(RS.norm).str.lower()
    excluded = category.str.contains('استند|تستر|کاتالوگ|پوستر|تبلیغاتی|نمونه|posm|tester|stand', regex=True)
    excluded |= category.isin(['', 'سایر', 'نامشخص', 'بدون گروه'])
    quality_sales = sales[~excluded]
    quality_totals = {col: float(quality_sales[col].sum()) for col in ('gross', 'net', 'cash', 'mgmt', 'tax')}
    quality_totals['other_disc'] = quality_totals['gross'] + quality_totals['tax'] - quality_totals['net'] - quality_totals['cash'] - quality_totals['mgmt']
    quality_totals['discount'] = quality_totals['gross'] + quality_totals['tax'] - quality_totals['net']
    for rate, amount in [('disc_rate', 'discount'), ('cash_rate', 'cash'),
                         ('mgmt_rate', 'mgmt'), ('other_rate', 'other_disc')]:
        quality_totals[rate] = quality_totals[amount] / quality_totals['gross'] if quality_totals['gross'] > 0 else None
    quality = {'kpis': quality_totals}
    for key, dim in [('countries', 'country'), ('customers', 'code'), ('brands', 'brand'), ('categories', 'cat2')]:
        quality[key] = groups(dim, quality_sales, prior.iloc[:0])

    kpis = dict(base['kpis'])
    for key in ('net', 'gross', 'pcs', 'req', 'req_pcs'):
        col = 'qty' if key == 'pcs' else key
        old = float(prior[col].sum())
        kpis[f'{key}_comparison'] = old
        kpis[f'{key}_growth'] = kpis[key] / old - 1 if old else None
    kpis['zero_amount_qty'] = float(sales.loc[sales.net.eq(0) & sales.qty.gt(0), 'qty'].sum())
    kpis['countries'] = int(sales.loc[sales.qty.gt(0), 'country'].nunique())
    kpis['customers'] = int(sales.loc[sales.qty.gt(0), 'code'].nunique())
    kpis['customers_inactive'] = max(0, kpis['customers_total'] - kpis['customers'])
    trend = [{**row, 'future': row['mm'] > cutoff[5:7]} for row in EX._monthly(current, prior)]
    return {'year': year, 'compare_year': baseline, 'years': years, 'current': base['current'],
            'today': snap['today'], 'comparison_rule': 'همان ماه‌های انتخاب‌شده؛ سال جاری تا همان روز در سال مقایسه و سال‌های بسته تا پایان سال',
            'kpis': kpis, 'countries': groups('country'), 'customers': groups('code'),
            'brands': groups('brand'), 'categories': groups('cat2'), 'trend': trend,
            'goods': RS.build_tree(sales, previous_sales), 'sku': A.records(base['sku']),
            'quality': quality, 'options': base['options']}

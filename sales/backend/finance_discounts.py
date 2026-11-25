"""Discount drill-down for the finance dashboard."""
import pandas as pd

import analytics as A
import sql_source


AMOUNTS = ['gross', 'discount', 'cash', 'mgmt', 'volume', 'other']


def karamad_registered_discounts(env_file, invoice_id):
    return _karamad_registered_by_invoice(env_file, [invoice_id]).get(invoice_id, [])


def karamad_invoice_rates(env_file, invoice_ids):
    result = {}
    for invoice_id, items in _karamad_registered_by_invoice(env_file, invoice_ids).items():
        result[str(invoice_id)] = {
            key: [{'pct': pct} for pct in dict.fromkeys(entry['pct'] for item in items for entry in item[key])]
            for key in ('mgmt', 'cash', 'volume')
        }
    return result


def _karamad_registered_by_invoice(env_file, invoice_ids):
    """Read saved policies in batches, preserving invoice and line identity."""
    cfg = sql_source.settings(sql_source.read_env(env_file))
    connection = sql_source.connect(cfg)
    try:
        connection.timeout = 10
        result = {}
        for offset in range(0, len(invoice_ids), 500):
            batch = invoice_ids[offset:offset + 500]
            params = ','.join('?' for _ in batch)
            rows = sql_source._read(connection, f"""
                SELECT v.ID AS invoice_id, v.[row] AS line_no, v.GoodsCode AS product_code, v.GoodsName AS product,
                       v.TotalT AS qty, v.CashDiscount AS cash_amount, v.CashPercent AS cash_pct,
                       d.FactorRef AS has_policy, a.Name AS policy, a.IsCashDiscount AS is_cash,
                       d.Per AS registered_pct
                FROM dbo.vwFactorFBLinesFull v
                LEFT JOIN dbo.tblFactorfDiscount d ON v.ID = d.FactorRef AND v.[row] = d.RowRef
                LEFT JOIN dbo.tblAccDiscount a ON a.ID = d.DiscountRef
                WHERE v.ID IN ({params}) AND v.FactorType = N'فروش'
                ORDER BY v.ID, line_no, d.inx
            """, batch)
            for invoice_id, invoice in rows.groupby('invoice_id', sort=False):
                result[invoice_id] = _karamad_items(A.records(invoice))
        return result
    finally:
        connection.close()


def _karamad_items(records):
    items = {}
    cash_fields = {}
    for row in records:
        line = row['line_no']
        if line not in items:
            items[line] = {key: row[key] for key in ('line_no', 'product_code', 'product', 'qty')}
            items[line].update(mgmt=[], cash=[], volume=[])
            cash_fields[line] = (row['cash_pct'], row['cash_amount'])
        if row['has_policy'] is None:
            continue
        policy = sql_source.loader._clean_text(row['policy'])
        if policy in sql_source.MGMT_NAMES:
            category = 'mgmt'
        elif row['is_cash'] or policy == 'تخفیف نقدی':
            category = 'cash'
        else:
            category = 'volume'
        items[line][category].append({'policy': policy, 'pct': row['registered_pct']})
    for line, item in items.items():
        pct, amount = cash_fields[line]
        if item['cash']:
            # A zero CashPercent can coexist with a real cash policy (e.g. 22%).
            if pct and all(entry['pct'] != pct for entry in item['cash']):
                item['cash'].append({'policy': 'تخفیف نقدی ردیف', 'pct': pct})
        elif pct is not None or amount:
            item['cash'].append({'policy': 'تخفیف نقدی', 'pct': pct})
    return list(items.values())


def normalize(lines: pd.DataFrame, source: str) -> pd.DataFrame:
    if source == 'karamad':
        rows = lines.loc[~lines.is_return].copy().rename(columns={
            'branch': 'group', 'inv_no': 'invoice', 'inv_id': 'invoice_id',
            'disc': 'discount', 'cash_disc': 'cash', 'mgmt_disc': 'mgmt', 'vol_disc': 'volume',
        })
    else:
        rows = lines.loc[lines.kind.eq('S')].copy().rename(columns={
            'province' if source == 'b2b' else 'country': 'group',
            'inv': 'invoice', 'short': 'customer',
        })
        if source == 'export':
            # Export has a single discount total regardless of policy title.
            rows = rows.loc[rows.gross.ne(0) | rows.discount.ne(0)].copy()
            rows[['cash', 'mgmt', 'volume']] = 0.0

    for name in ('group', 'customer', 'invoice', 'invoice_id', 'product_code', 'product'):
        if name not in rows:
            rows[name] = ''
        rows[name] = rows[name].fillna('').astype(str)
    rows['group'] = rows.group.replace('', 'نامشخص')
    rows['invoice_id'] = rows.invoice_id.where(rows.invoice_id.ne(''), rows.invoice)
    rows['other'] = rows.discount - rows.cash - rows.mgmt - rows.volume
    return rows


def with_rates(frame: pd.DataFrame) -> pd.DataFrame:
    gross = frame.gross.where(frame.gross > 0)
    return frame.assign(**{f'{key}_rate': frame[key] / gross for key in AMOUNTS[1:]})


def report(lines, source, today, date_from=None, date_to=None, group=None, invoice_id=None):
    rows = normalize(lines, source)
    end = date_to or today
    start = date_from or end[:7] + '/01'
    latest_month = False
    if source in ('b2b', 'export') and not date_from and not date_to:
        eligible = rows.loc[rows.date.le(today), 'date']
        if not eligible.empty and eligible.max() < start:
            end = eligible.max()
            start = end[:7] + '/01'
            latest_month = True
    selected = rows.loc[rows.date.between(start, end)]
    if group is None:
        totals = selected[AMOUNTS].sum().to_frame().T
        groups = selected.groupby('group', observed=True)[AMOUNTS].sum().reset_index()
        return {
            'today': today,
            'dates': sorted(rows.date.unique().tolist()),
            'period': {'from': start, 'to': end, 'latest_month': latest_month},
            'total': A.records(with_rates(totals))[0],
            'rows': A.records(with_rates(groups).sort_values('discount_rate', ascending=False)),
        }
    selected = selected.loc[selected.group.eq(group)]
    keys = ['invoice_id', 'invoice', 'date', 'customer']
    if invoice_id is None:
        invoices = selected.groupby(keys, observed=True)[AMOUNTS].sum().reset_index()
        return {'rows': A.records(with_rates(invoices).sort_values(['date', 'invoice'], ascending=False))}
    selected = selected.loc[selected.invoice_id.eq(invoice_id)]
    item_keys = ['item_id'] if source == 'export' and 'item_id' in selected else []
    items = selected[keys + item_keys + ['product_code', 'product', 'qty', *AMOUNTS]]
    if source != 'karamad':
        items = with_rates(items)
    return {'rows': A.records(items)}

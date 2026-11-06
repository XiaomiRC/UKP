"""Excel outputs (same layout as the chat's files) and the Power BI dataset (CSV star schema)."""
from __future__ import annotations

import os
import re
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HF = Font(name='Arial', bold=True, color='FFFFFF', size=10)
HX = PatternFill('solid', fgColor='1F4E78')
BASE = Font(name='Arial', size=10)
BOLD = Font(name='Arial', bold=True, size=10)
NOTE = Font(name='Arial', italic=True, size=9, color='555555')
THIN = Border(*[Side(style='thin', color='D9D9D9')] * 4)
FILL = {'In Both': 'E2EFDA', 'In SAC only': 'FFF2CC', 'In OneBill only': 'FCE4EC',
        'High': 'FCE4EC', 'Medium': 'FFF2CC', 'Low': 'DDEBF7', 'Info': 'F2F2F2',
        'PASS': 'E2EFDA', 'WARN': 'FFF2CC', 'FAIL': 'FCE4EC', 'INFO': 'F2F2F2', 'Yes': 'E2EFDA', 'No': 'FCE4EC',
        'Ties': 'E2EFDA', 'Gap': 'FFF2CC'}
MONEY_WORDS = ('£', 'Amount', 'Revenue', 'Cost', 'Margin', 'Rate', 'Difference', 'rental', 'Impact', 'Costs')


def _sheet(wb, title, df: pd.DataFrame, color_col=None, note=None, widths=None):
    ws = wb.create_sheet(title[:31])
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and pd.isna(v)) else
                   (v.to_pydatetime().date() if isinstance(v, pd.Timestamp) else v) for v in row])
    for c in ws[1]:
        c.font, c.fill = HF, HX
        c.alignment = Alignment(vertical='center', wrap_text=True)
    money = [i + 1 for i, c in enumerate(df.columns) if any(w in str(c) for w in MONEY_WORDS)]
    ci = list(df.columns).index(color_col) + 1 if color_col in df.columns else None
    for r in ws.iter_rows(min_row=2, max_row=ws.max_row):
        fill = PatternFill('solid', fgColor=FILL.get(str(r[ci - 1].value).split(' ')[0] if ci else '', 'FFFFFF')) if ci else None
        if ci and str(r[ci - 1].value) in FILL:
            fill = PatternFill('solid', fgColor=FILL[str(r[ci - 1].value)])
        for c in r:
            c.font, c.border = BASE, THIN
            c.alignment = Alignment(vertical='top', wrap_text=isinstance(c.value, str) and len(c.value) > 40)
            if fill is not None and ci:
                c.fill = fill
            if c.column in money:
                c.number_format = '#,##0.00'
    for i, col in enumerate(df.columns, 1):
        q = pd.Series([len(str(v)) for v in df.iloc[:, i - 1]], dtype=float).quantile(0.9) if len(df) else 10
        q = 10 if pd.isna(q) else q
        w = (widths or {}).get(col) or min(60, max(10, int(q) + 2, len(str(col)) + 2))
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A2'
    if len(df):
        ws.auto_filter.ref = ws.dimensions
    if note:
        n = ws.max_row + 2
        ws.cell(row=n, column=1, value=f'Source: {note}').font = NOTE
    return ws


def _kv_sheet(wb, title, header: str, rows: list[tuple], index=0):
    ws = wb.create_sheet(title, index)
    ws['A1'] = header
    ws['A1'].font = Font(name='Arial', bold=True, size=13)
    ws['A2'] = f'Generated {datetime.now():%d-%b-%Y %H:%M} by the UKP SAC Investigator (rule-based, no AI). ' \
               'Every figure is reproducible from the Data Sources sheet.'
    ws['A2'].font = NOTE
    r = 4
    for row in rows:
        for j, v in enumerate(row, 1):
            c = ws.cell(row=r, column=j, value=v)
            c.font = BOLD if len(row) == 1 or j == 1 and str(v).endswith(':') else BASE
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                c.number_format = '#,##0.00' if isinstance(v, float) else '#,##0'
        r += 1
    ws.column_dimensions['A'].width = 62
    for col in 'BCD':
        ws.column_dimensions[col].width = 18
    return ws


# ---------------------------------------------------------------------------------------------- Task 1
def write_reconciliation(res, out_dir: str) -> str:
    wb = Workbook()
    wb.remove(wb.active)
    s = res.summary
    acc = res.accounts.drop(columns=['SAC'])
    _sheet(wb, 'Account Reconciliation', acc, 'Status',
           'SAC report → Enterprise tab (Billing Account Number, Discounted Price) vs OneBill CSVs (Source account, '
           'Total charges before VAT). Shared bills filtered to this customer\'s lines — see Bill File Issues.')
    if len(res.services):
        _sheet(wb, 'Service Level Detail', res.services.drop(columns=['SAC']), 'Matched in SAC',
               'OneBill Service number (suffix /0001 removed) vs SAC Telephone Number / Service ID / Billing Account.')
    iss = pd.DataFrame(res.issues, columns=['File', 'OneBill', 'Issue', 'Detail', 'Impact'])
    _sheet(wb, 'Bill File Issues', iss, widths={'Detail': 70, 'Impact': 60, 'File': 40})
    _sheet(wb, 'Bills Used', res.bills.drop(columns=['SAC']) if len(res.bills) else res.bills, 'BillType')
    _sheet(wb, 'Checks', pd.DataFrame(res.checks).drop(columns=['SAC']), 'Result')
    reasons = res.accounts[res.accounts['Status'] != 'In Both'].groupby(['Status', 'Reason']).agg(
        Accounts=('Billing Account', 'size'), SAC=('SAC Amount', 'sum'), Bill=('OneBill Amount', 'sum')).reset_index()
    rows = [('Account-level results:', 'Accounts', '£ SAC report', '£ OneBill')]
    for st in ('In Both', 'In SAC only', 'In OneBill only'):
        rows.append((st, s[f'{st} (count)'], s[f'{st} (£ SAC)'], s[f'{st} (£ bill)']))
    rows += [(), ('Totals:',), ('SAC report monthly total (Discounted Price, ex VAT)', '', s['SAC monthly total']),
             ('OneBill lines used (ex VAT)', s['Bill lines used'], '', s['Bill total used']),
             ('Service lines matched to SAC', f"{s['Service lines matched']} of {s['Service lines total']}"),
             ('Accounts to chase (on a supplied bill per SAC but not billed)', s['Chase items']),
             (), ('Why things are unmatched:', 'Accounts', '£ SAC report', '£ OneBill')]
    rows += [(f"{r.Status} — {r.Reason}", int(r.Accounts), round(r.SAC, 2), round(r.Bill, 2)) for r in reasons.itertuples()]
    _kv_sheet(wb, 'Summary', f'SAC vs OneBill reconciliation — {res.sac} {res.customer}', rows)
    path = os.path.join(out_dir, f'SAC_vs_OneBill_Reconciliation_{res.sac}.xlsx')
    wb.save(path)
    return path


# ---------------------------------------------------------------------------------------------- Task 2
def write_deepdive(dd, out_dir: str, recon=None) -> str:
    wb = Workbook()
    wb.remove(wb.active)
    h = dd.headline
    P = dd.period
    hi = dd.findings[dd.findings['Severity'].isin(['High', 'Medium'])]
    rows = [('Headline:',),
            (f'FY26 {P} YTD revenue', h['FY26 YTD Revenue']), (f'FY26 {P} YTD cost', h['FY26 YTD Cost']),
            (f'FY26 {P} YTD margin', h['FY26 YTD Margin']), ('FY25 revenue', h['FY25 Revenue']),
            ('FY25 margin', h['FY25 Margin']), ('World Key', h['World Key'] or '(none)'),
            ('Circuits mapped / live', f"{h['Mapped circuits']} / {h['Live circuits']}"),
            (f'Live circuit rental ({P})', h[f'Circuit rental {P}']),
            ('Voice accounts costed under this SAC', h['Voice accounts']),
            ('…of which in the SAC 360 report', h['Voice accounts in SAC report']), (),
            ('Findings (High / Medium):',)]
    rows += [(f"[{f.Severity}] {f.Product}: {f.Flag}", f.Finding) for f in hi.itertuples()]
    if recon is not None:
        s = recon.summary
        rows += [(), ('Billing context (SAC vs OneBill reconciliation):',),
                 ('Accounts in both / SAC only / OneBill only',
                  f"{s['In Both (count)']} / {s['In SAC only (count)']} / {s['In OneBill only (count)']}"),
                 ('OneBill amount used (ex VAT)', s['Bill total used']), ('SAC report monthly total', s['SAC monthly total'])]
    ws = _kv_sheet(wb, 'Executive Summary', f'UKP deep dive — {dd.sac} {dd.customer} ({P} 2026)', rows)
    ws.column_dimensions['B'].width = 110
    for r in ws.iter_rows(min_row=4):
        r[1].alignment = Alignment(wrap_text=True, vertical='top')

    src = {r['Analysis item']: f"{r['Source file']} → {r['Tab']} → {r['How to reproduce']}" for _, r in dd.sources.iterrows()}
    _sheet(wb, 'Findings', dd.findings.drop(columns=['SAC']), 'Severity',
           widths={'Finding': 80, 'Action': 50, 'Source': 50})
    _sheet(wb, 'P&L by Product', dd.product_summary.drop(columns=['SAC']), None,
           src.get('UKP P&L FY26 YTD (by product, period, entity, type)'))
    trend = dd.pnl[dd.pnl['FY'] == 'FY26'].pivot_table(index=['Product', 'Type'], columns='Period',
                                                       values=['Revenue', 'Cost', 'Margin'], aggfunc='sum').fillna(0)
    trend.columns = [f'{a} {b}' for a, b in trend.columns]
    _sheet(wb, 'Monthly Trend FY26', trend.reset_index().round(2), None,
           src.get('UKP P&L FY26 YTD (by product, period, entity, type)'))
    _sheet(wb, 'P&L Detail', dd.pnl.drop(columns=['SAC']), None,
           'FY26 rows: WD4 → Data; FY25 rows: 24-month report → PY-Data (filter SAC).')
    _sheet(wb, 'Circuit Evidence', dd.circuits.drop(columns=['SAC']), None,
           src.get('Circuits mapped to the SAC', '') + ' | ' + src.get(f'Circuit monthly rental ({P})', ''))
    if len(dd.circuit_tie):
        _sheet(wb, 'Circuit Tie-out', dd.circuit_tie.drop(columns=['SAC']), 'Tie-out')
    _sheet(wb, 'Voice Evidence', dd.voice_tie.drop(columns=['SAC']), None, src.get(f'Voice inventory ({P})'))
    _sheet(wb, 'Mapping Evidence', dd.mapping, None, src.get('Customer-name mapping'), widths={'Customer Name': 50})
    _sheet(wb, 'Checks', pd.DataFrame(dd.checks).drop(columns=['SAC']), 'Result')
    _sheet(wb, 'Data Sources', dd.sources.drop(columns=['SAC']), None,
           'Note: the circuit-mapping "SAC " header has a trailing space; START_DATE/END_DATE in the product extract are '
           'Excel serial dates (e.g. 46266 = 01-Sep-2026).', widths={'How to reproduce': 90, 'Source file': 60})
    path = os.path.join(out_dir, f'{dd.sac}_UKP_Deep_Dive_Analysis.xlsx')
    wb.save(path)
    return path


TRACKER_HEADER_1 = [None] * 10 + ['Revenue', 'Margin ', 'FY25 Revenue Reported', 'FY25 Margin Reported', None]


def write_tracker(dd, out_dir: str) -> str:
    """Same two-row header as the user's 'UKP tracker.xlsx' Summary sheet."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Summary'
    P = dd.period
    ws.append(TRACKER_HEADER_1)
    ws.append(['Resource Name', 'Contract Name', 'SAC code', 'Product', 'Issue type', 'Findings', 'Billing account',
               'Circuit ID', 'Impacted Revenue', 'Action Log', f'{P}(YTD)', f'{P}(YTD)', None, None, 'Comment'])
    for r in dd.tracker.itertuples(index=False):
        ws.append(list(r))
    for row in ws.iter_rows(min_row=1, max_row=2):
        for c in row:
            c.font, c.fill = HF, HX
            c.alignment = Alignment(wrap_text=True, vertical='center')
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row):
        for c in row:
            c.font, c.border = BASE, THIN
            c.alignment = Alignment(wrap_text=True, vertical='top')
            if c.column in (9, 11, 12, 13, 14):
                c.number_format = '#,##0.00'
    n = ws.max_row
    ws.append([None] * 9 + ['Total (check = UKP P&L)', f'=SUM(K3:K{n})', f'=SUM(L3:L{n})', f'=SUM(M3:M{n})', f'=SUM(N3:N{n})'])
    for c in ws[ws.max_row]:
        c.font = BOLD
        c.number_format = '#,##0.00'
    for col, w in zip('ABCDEFGHIJKLMNO', [16, 30, 10, 28, 22, 80, 22, 22, 14, 50, 13, 13, 15, 15, 60]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = 'A3'
    path = os.path.join(out_dir, f'{dd.sac}_UKP_Tracker_Format.xlsx')
    wb.save(path)
    return path


# ---------------------------------------------------------------------------------------------- Power BI dataset
def _stable(col: str) -> str:
    """Power BI needs the same column names every period: drop period tags and the £ sign."""
    col = re.sub(r'\s*\(P\d{2}\)|\s+P\d{2}\b', '', str(col))
    return col.replace('£ ', 'GBP ').replace(' £', ' GBP').replace('£', 'GBP').strip()


def _upsert(path: str, df: pd.DataFrame, sac: str):
    df = df.rename(columns=_stable)
    if 'SAC' not in df:
        df = df.assign(SAC=pd.Series(dtype=str))
    if os.path.exists(path):
        old = pd.read_csv(path, dtype={'SAC': str})
        old = old[old['SAC'].astype(str) != sac]
        df = pd.concat([old, df], ignore_index=True)
    temp = path + '.tmp'
    df.to_csv(temp, index=False)
    os.replace(temp, path)


def write_dataset(ds_dir: str, sac: str, recon=None, dd=None, run_info: dict | None = None):
    """Write/replace this SAC's rows in each CSV table (other SACs are kept), so the dataset grows per run."""
    os.makedirs(ds_dir, exist_ok=True)
    head = dict(dd.headline) if dd is not None else {'SAC': sac, 'Customer': recon.customer if recon else ''}
    if recon is not None:
        head.update({k: v for k, v in recon.summary.items() if k not in ('SAC', 'Customer')})
    head.update(run_info or {})
    head = {_stable(k): v for k, v in head.items()}
    hp = os.path.join(ds_dir, 'dim_sac.csv')
    if os.path.exists(hp):
        previous = pd.read_csv(hp, dtype={'SAC': str})
        previous = previous[previous['SAC'] == sac]
        if len(previous):
            head = {**previous.iloc[0].to_dict(), **head}
    _upsert(os.path.join(ds_dir, 'dim_sac.csv'), pd.DataFrame([head]), sac)
    checks = []
    if recon is not None:
        _upsert(os.path.join(ds_dir, 'fact_recon_account.csv'), recon.accounts, sac)
        if True:
            _upsert(os.path.join(ds_dir, 'fact_recon_service.csv'), recon.services, sac)
        _upsert(os.path.join(ds_dir, 'dim_bill.csv'), recon.bills, sac)
        iss = pd.DataFrame(recon.issues, columns=['File', 'OneBill', 'Issue', 'Detail', 'Impact'])
        iss.insert(0, 'SAC', sac)
        _upsert(os.path.join(ds_dir, 'fact_bill_issues.csv'), iss, sac)
        checks += recon.checks
    if dd is not None:
        _upsert(os.path.join(ds_dir, 'fact_pnl.csv'), dd.pnl, sac)
        _upsert(os.path.join(ds_dir, 'fact_product.csv'), dd.product_summary, sac)
        _upsert(os.path.join(ds_dir, 'fact_circuit.csv'), dd.circuits, sac)
        if True:
            _upsert(os.path.join(ds_dir, 'fact_circuit_tie.csv'), dd.circuit_tie, sac)
        _upsert(os.path.join(ds_dir, 'fact_findings.csv'), dd.findings, sac)
        _upsert(os.path.join(ds_dir, 'fact_sources.csv'), dd.sources, sac)
        checks += dd.checks
    cp = os.path.join(ds_dir, 'fact_checks.csv')
    if os.path.exists(cp):
        prior = pd.read_csv(cp, dtype={'SAC': str})
        owned = {'Bill files', 'Reconciliation'} if recon is not None else set()
        retain = prior[(prior['SAC'] == sac) & (~prior['Area'].isin(owned) if dd is None else prior['Area'].isin({'Bill files', 'Reconciliation'}) if recon is None else False)]
        checks += retain.to_dict('records')
    if checks:
        _upsert(os.path.join(ds_dir, 'fact_checks.csv'), pd.DataFrame(checks), sac)

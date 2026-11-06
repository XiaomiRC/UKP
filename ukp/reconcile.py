"""Task 1: SAC report vs OneBill reconciliation (deterministic).

Matching (same keys as the chat's sacrecon.py):
  account level : SAC 'Billing Account Number'  <->  bill 'Source account' (or Service number when blank)
  service level : bill 'Service number' (with /0001 removed) <-> SAC Telephone Number / Service ID / Billing Account
"""
from __future__ import annotations

from dataclasses import dataclass, field

import os
import numpy as np
import pandas as pd

from .bills import prepare_bills
from .loaders import BILL_TOTAL, BillFile, SacReport

STATUS_ORDER = {'In Both': 0, 'In SAC only': 1, 'In OneBill only': 2}


@dataclass
class ReconResult:
    sac: str
    customer: str
    accounts: pd.DataFrame
    services: pd.DataFrame
    issues: list
    checks: list
    bills: pd.DataFrame
    sac_rows: pd.DataFrame
    summary: dict = field(default_factory=dict)


def _join(s: pd.Series) -> str:
    return ', '.join(sorted(set(s.dropna().astype(str).str.strip()) - {''}))


def reconcile(rep: SacReport, bill_files: list[BillFile], cfg: dict) -> ReconResult:
    rc = cfg['reconciliation']
    mobile = set(rc['mobile_billing_systems'])
    lines, issues, checks, bill_dim = prepare_bills(rep, bill_files, cfg)
    supplied = set(bill_dim['OneBill']) if len(bill_dim) else set()
    empty = set(bill_dim.loc[bill_dim['BillType'] == 'Empty', 'OneBill']) if len(bill_dim) else set()
    ob_status = dict(zip(rep.onebills['OneBill'], rep.onebills['Status'])) if len(rep.onebills) else {}
    ref_date = pd.Timestamp(os.environ.get('UKP_REPORTING_DATE') or pd.Timestamp.today()).normalize()

    e = rep.ent[rep.ent['acct'] != '']
    sac = e.groupby('acct').agg(
        sub=('Sub Sector', _join), sys=('Billing System', _join), le=('Legal Entity Name', lambda s: _join(s)[:80]),
        ob_sac=('OneBill Account Number', _join), amt=('DP', 'sum'), rows=('acct', 'size'),
        products=('Product Name', lambda s: _join(s)[:120]), end=('ContractEnd', 'max')).reset_index()
    if len(lines):
        oba = lines.groupby('acctkey').agg(ob_act=('OneBill', _join), amt_ob=(BILL_TOTAL, 'sum'),
                                           rows_ob=('acctkey', 'size'), stype=('stype', _join)).reset_index()
        oba = oba.rename(columns={'acctkey': 'acct'})
    else:
        oba = pd.DataFrame(columns=['acct', 'ob_act', 'amt_ob', 'rows_ob', 'stype'])
    rec = sac.merge(oba, on='acct', how='outer')
    both = rec['rows'].notna() & rec['rows_ob'].notna()
    rec['Status'] = np.where(both, 'In Both', np.where(rec['rows'].notna(), 'In SAC only', 'In OneBill only'))

    def reason(r):
        if r['Status'] == 'In Both':
            a, b = r['amt'] or 0, r['amt_ob'] or 0
            if a == 0 and b > 0:
                return 'Matched — £0 in SAC report but billed'
            if a > 0 and b > 2.5 * a and b - a > 50:
                return 'Matched — billed far above SAC price (SAC may hold only an add-on/increment)'
            return 'Matched'
        if r['Status'] == 'In OneBill only':
            if str(r['acct']).startswith('VP'):
                return 'OneBill-level charge (no source account)'
            if (r['amt_ob'] or 0) < 0:
                return 'Credit on bill, account not in SAC report'
            return 'Billed but not in SAC report'
        o = '' if pd.isna(r['ob_sac']) else str(r['ob_sac'])
        s = '' if pd.isna(r['sys']) else str(r['sys'])
        ended = pd.notna(r['end']) and r['end'] < ref_date
        if o:
            vps = [v.strip() for v in o.split(',')]
            if any(v in empty for v in vps):
                return f'SAC bill {o} supplied but the file is empty'
            if not any(v in supplied for v in vps):
                st = ', '.join(sorted({ob_status.get(v, '') for v in vps} - {''}))
                return f'SAC bill {o} not supplied' + (f' ({st})' if st else '')
            if ended:
                return f'On supplied bill {o} per SAC but not billed — contract ended {r["end"]:%b-%Y} (likely stale)'
            if (r['amt'] or 0) == 0:
                return f'On supplied bill {o} per SAC but not billed — £0 item'
            return f'On supplied bill {o} per SAC but not billed — CHASE'
        if s and set(s.split(', ')) <= mobile:
            return f'Mobile billing system ({s}) — not billed via OneBill'
        if not s:
            return ('No OneBill and no billing system — contract ended (likely stale)' if ended
                    else 'No OneBill and no billing system in SAC report')
        return f'No OneBill in SAC report ({s}) — billed elsewhere'

    rec['Reason'] = rec.apply(reason, axis=1)
    rec['Difference'] = rec['amt'].fillna(0) - rec['amt_ob'].fillna(0)
    rec = rec.sort_values(['Status', 'Reason', 'acct'],
                          key=lambda s: s.map(STATUS_ORDER) if s.name == 'Status' else s).reset_index(drop=True)
    rec.insert(0, 'SAC', rep.sac)
    accounts = rec.rename(columns={
        'acct': 'Billing Account', 'sub': 'Sub Sector', 'sys': 'Billing System', 'le': 'Legal Entity',
        'ob_sac': 'OneBill (per SAC)', 'ob_act': 'OneBill (actual)', 'amt': 'SAC Amount',
        'amt_ob': 'OneBill Amount', 'rows': 'SAC Rows', 'rows_ob': 'OneBill Rows',
        'products': 'SAC Products', 'stype': 'Bill Service Types', 'end': 'Latest Contract End'})

    # ---- service level
    def index(col):
        d = rep.ent[rep.ent[col].str.strip() != ''].copy()
        d['k'] = d[col].str.upper().str.strip()
        return d.drop_duplicates('k').set_index('k')
    mt, ms, ma = index('Telephone Number'), index('Service ID'), index('Billing Account Number')
    svc = []
    lines = lines.assign(amtx=lines[BILL_TOTAL]) if len(lines) else lines
    for r in (lines[['OneBill', 'svc', 'svc_base', 'src', 'stype', 'amtx']].itertuples(index=False) if len(lines) else []):
        hit, how = None, ''
        for key, m, lab in [(r.svc, mt, 'Telephone Number'), (r.svc, ms, 'Service ID'),
                            (r.svc_base, mt, 'Telephone Number (/suffix removed)'),
                            (r.svc_base, ms, 'Service ID (/suffix removed)'),
                            (r.src, ma, 'Source account = SAC Billing Account'),
                            (r.svc_base, ma, 'Service no. = SAC Billing Account')]:
            if key and key in m.index:
                hit, how = m.loc[key], lab
                break
        svc.append({'SAC': rep.sac, 'OneBill': r.OneBill, 'Service Number': r.svc, 'Source Account': r.src,
                    'Service Type': r.stype, 'OneBill Amount': round(float(r.amtx), 2),
                    'Matched in SAC': 'Yes' if hit is not None else 'No', 'Matched Via': how,
                    'Sub Sector': '' if hit is None else hit['Sub Sector'],
                    'SAC Billing Account': '' if hit is None else hit['acct'],
                    'SAC Amount': None if hit is None else round(float(hit['DP']), 2),
                    'SAC Product': '' if hit is None else hit['Product Name']})
    services = pd.DataFrame(svc)
    if len(services):
        services = services.sort_values(['Matched in SAC', 'OneBill', 'Service Number'],
                                        key=lambda s: s.map({'Yes': 0, 'No': 1}) if s.name == 'Matched in SAC' else s)

    # ---- summary + control checks
    g = accounts.groupby('Status')
    summ = {
        'SAC': rep.sac, 'Customer': rep.customer,
        'Accounts in SAC report': int(accounts['SAC Rows'].notna().sum()),
        'SAC monthly total': round(float(rep.ent['DP'].sum()), 2),
        'Bill lines used': int(len(lines)), 'Bill total used': round(float(lines[BILL_TOTAL].sum()) if len(lines) else 0, 2),
    }
    for st in STATUS_ORDER:
        sub = accounts[accounts['Status'] == st]
        summ[f'{st} (count)'] = int(len(sub))
        summ[f'{st} (£ SAC)'] = round(float(sub['SAC Amount'].fillna(0).sum()), 2)
        summ[f'{st} (£ bill)'] = round(float(sub['OneBill Amount'].fillna(0).sum()), 2)
    summ['Service lines matched'] = int((services['Matched in SAC'] == 'Yes').sum()) if len(services) else 0
    summ['Service lines total'] = int(len(services))
    summ['Chase items'] = int(accounts['Reason'].str.contains('CHASE').sum())

    def chk(check, ok, value, detail=''):
        checks.append({'SAC': rep.sac, 'Area': 'Reconciliation', 'Check': check,
                       'Result': 'PASS' if ok else 'FAIL', 'Value': value, 'Detail': detail})
    tot_bill = float(accounts['OneBill Amount'].fillna(0).sum())
    chk('Account-level bill £ = bill lines used £', abs(tot_bill - summ['Bill total used']) < 0.05,
        round(tot_bill, 2), f"lines {summ['Bill total used']:,.2f}")
    tot_sac = float(accounts['SAC Amount'].fillna(0).sum())
    sac_acct_total = float(rep.ent.loc[rep.ent['acct'] != '', 'DP'].sum())
    chk('Account-level SAC £ = SAC report total (rows with an account)', abs(tot_sac - sac_acct_total) < 0.05,
        round(tot_sac, 2), f'SAC report {sac_acct_total:,.2f}')
    chk('Every account has exactly one status', accounts['Billing Account'].is_unique, len(accounts))
    return ReconResult(rep.sac, rep.customer, accounts, services, issues, checks, bill_dim, rep.ent, summ)

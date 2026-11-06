"""Bill-file checks and shared (bulk) bill filtering — the rules that the AI runs got wrong.

Every decision is written to `issues` (shown on the Bill File Issues sheet) and `checks`
(the Accuracy & Controls page), so nothing is silently dropped.
"""
from __future__ import annotations

import hashlib
import os
from collections import Counter

import pandas as pd

from .loaders import BILL_TOTAL, BillFile, SacReport


def _md5(path: str) -> str:
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def sac_keys(rep: SacReport) -> tuple[set, set]:
    """Account numbers and service identifiers (phone numbers / service IDs) in the SAC report."""
    e = rep.ent
    accts = set(e['acct']) - {''}
    svcs = set(e['Telephone Number'].str.upper()) | set(e['Service ID'].str.upper())
    return accts, svcs - {''}


def line_in_sac(df: pd.DataFrame, accts: set, svcs: set) -> pd.Series:
    return (df['acctkey'].isin(accts) | df['svc'].isin(svcs) | df['svc_base'].isin(svcs)
            | df['svc_base'].isin(accts))


def prepare_bills(rep: SacReport, bills: list[BillFile], cfg: dict):
    """Run all bill-file checks and return (lines_used, issues, checks, bill_dim)."""
    rc = cfg['reconciliation']
    accts, svcs = sac_keys(rep)
    issues, checks, used, dim = [], [], [], []
    ob_tab = rep.onebills.set_index('OneBill') if len(rep.onebills) else pd.DataFrame()

    def chk(check, result, value='', detail=''):
        checks.append({'SAC': rep.sac, 'Area': 'Bill files', 'Check': check, 'Result': result,
                       'Value': value, 'Detail': detail})

    # duplicate files (identical content)
    hashes = {}
    dates = Counter(b.bill_date for b in bills if b.bill_date and len(b.df))
    main_date = dates.most_common(1)[0][0] if dates else ''

    for b in bills:
        base = os.path.basename(b.path)
        vp = b.rows_vp or b.file_vp
        if len(b.df) == 0:
            issues.append((base, b.file_vp, 'Empty file', 'The file is 0 bytes / has no lines.',
                           f'Accounts the SAC report places on {b.file_vp} will show as "In SAC only". Re-download this bill.'))
            chk(f'{b.file_vp}: file has data', 'FAIL', 0, 'Empty file')
            dim.append({'SAC': rep.sac, 'OneBill': b.file_vp, 'File': base, 'BillType': 'Empty', 'Lines': 0,
                        'Lines used': 0, 'Amount (all lines)': 0.0, 'Amount (used)': 0.0, 'Bill date': b.bill_date,
                        'Issue': 'Empty file'})
            continue
        h = _md5(b.path)
        if h in hashes:
            issues.append((base, vp, 'Duplicate file', f'Identical content to {hashes[h]}.', 'Counted once only.'))
            chk(f'{base}: duplicate', 'WARN', '', f'same as {hashes[h]}')
            continue
        hashes[h] = base
        issue_txt = []
        if b.file_vp and b.rows_vp and b.file_vp != b.rows_vp:
            issues.append((base, b.rows_vp, 'File name ≠ bill in rows',
                           f'File is named {b.file_vp} but every row is for {b.rows_vp}.',
                           f'Treated as bill {b.rows_vp}. {b.file_vp} itself is still outstanding.'))
            chk(f'{b.file_vp}: file name matches rows', 'WARN', b.rows_vp, 'mislabelled file')
            issue_txt.append(f'Named {b.file_vp}')
        if main_date and b.bill_date and b.bill_date != main_date:
            issues.append((base, vp, 'Different bill date', f'Bill dated {b.bill_date}; the others are {main_date}.',
                           'Fine for presence checks; amounts are from a different month.'))
            issue_txt.append(f'Dated {b.bill_date}')
        lines_total = float(b.df[BILL_TOTAL].sum())
        if b.total_row is not None:
            ok = abs(lines_total - b.total_row) < 0.05
            chk(f'{vp}: lines sum to the bill Total row', 'PASS' if ok else 'FAIL',
                round(lines_total, 2), f'Total row {b.total_row:,.2f}')
        if (b.df[BILL_TOTAL] <= 0).all():
            issues.append((base, vp, 'Credit-only bill', f'Every line is a credit (total {lines_total:,.2f}).',
                           'Not a current bill; amounts are credits only.'))
            issue_txt.append('Credit-only')
        long_lines = (b.df['rent_days'] > rc['multi_month_rental_days']).sum()
        if long_lines:
            mx = int(b.df['rent_days'].max())
            issues.append((base, vp, 'Multi-month billing',
                           f'{long_lines} lines cover more than {rc["multi_month_rental_days"]} rental days (up to {mx}).',
                           'Bill amounts can be 2–3× the SAC monthly price; that is expected.'))
            issue_txt.append(f'Up to {mx} rental days')

        in_sac = line_in_sac(b.df, accts, svcs)
        n_acc = b.df['acctkey'].nunique()
        share = b.df.loc[in_sac, 'acctkey'].nunique() / n_acc if n_acc else 0
        tab_type = ob_tab.loc[vp, 'BillType'] if vp in ob_tab.index else ''
        listed = vp in ob_tab.index
        auto_bulk = n_acc > rc['bulk_min_accounts'] and share < rc['bulk_max_match_share']
        if tab_type == 'Dedicated':
            btype = 'Dedicated'
        elif tab_type == 'Bulk' or vp in rc['known_bulk_bills'] or auto_bulk:
            btype = 'Shared (bulk)'
        else:
            btype = 'Dedicated'
        if btype == 'Shared (bulk)':
            keep = b.df[in_sac]
            why = ('SAC report Onebill tab says Bulk/MSfBT' if tab_type == 'Bulk' else
                   'listed in config known_bulk_bills' if vp in rc['known_bulk_bills'] else
                   f'auto-detected: only {share:.0%} of its {n_acc} accounts are in the SAC report')
            issues.append((base, vp, 'Shared (bulk) bill — filtered',
                           f'{why}. Kept {len(keep)} of {len(b.df)} lines ({keep[BILL_TOTAL].sum():,.2f} of {lines_total:,.2f}).',
                           'Only this customer\'s lines are reconciled; the rest belong to other customers.'))
            chk(f'{vp}: shared-bill filter applied', 'PASS', len(keep), why)
            issue_txt.append('Shared bill')
        else:
            keep = b.df
            if not listed and len(ob_tab):
                issues.append((base, vp, 'Bill not in SAC Onebill tab',
                               f'{vp} is not listed on the SAC report Onebill tab; {share:.0%} of its accounts match.',
                               'Check this bill belongs to the customer.'))
                chk(f'{vp}: listed in SAC Onebill tab', 'WARN', f'{share:.0%}', 'not listed')
        used.append(keep)
        dim.append({'SAC': rep.sac, 'OneBill': vp, 'File': base, 'BillType': btype, 'Lines': len(b.df),
                    'Lines used': len(keep), 'Amount (all lines)': round(lines_total, 2),
                    'Amount (used)': round(float(keep[BILL_TOTAL].sum()), 2), 'Bill date': b.bill_date,
                    'Issue': '; '.join(issue_txt)})

    supplied = {d['OneBill'] for d in dim} | {b.file_vp for b in bills}
    for vp, r in (ob_tab.iterrows() if len(ob_tab) else []):
        if vp not in supplied:
            st = r['Status'] or 'status blank'
            issues.append(('(not supplied)', vp, 'Bill in SAC report but not supplied',
                           f'SAC report Onebill tab lists {vp} ({st}).',
                           'Accounts on it will show as "In SAC only".'))
            chk(f'{vp}: bill supplied', 'WARN' if r['Status'] in ('Active', '') else 'INFO', '', st)

    lines = pd.concat(used, ignore_index=True) if used else pd.DataFrame(columns=['acctkey', 'OneBill', BILL_TOTAL])
    return lines, issues, checks, pd.DataFrame(dim)

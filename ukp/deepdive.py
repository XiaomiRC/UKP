"""Task 2: P06 deep-dive for one SAC — UKP P&L, circuit and voice evidence, mapping checks,
rule-based findings and UKP-tracker rows. Every table carries its source (file -> tab -> filter).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .loaders import PeriodFiles, SacReport

PERIODS = [f'P{i:02d}' for i in range(1, 13)]
SHEET_TO_PRODUCT = {
    'SHDS Data': 'SHDS CONNECT', 'IP CONNECT Data': 'IP Connect UK', 'OPTICAL CONNECT Data': 'Optical Connect UK',
    'ETHERNET CONNECT Data': 'Ethernet Connect National', 'INTERNET CONNECT Data': 'Btnet'}
VOICE_TO_PRODUCT = {'PSTN': 'PSTN', 'ISDN2': 'ISDN', 'ISDN30': 'ISDN', 'Featureline': 'Featureline'}
STOPWORDS = {'LTD', 'LIMITED', 'PLC', 'GROUP', 'THE', 'UK', 'SERVICES', 'SERVICE', 'CORPORATION', 'COMPANY',
             'OF', 'AND', 'BTSS', 'BTGS', 'HOLDINGS', 'INTERNATIONAL', 'TRUST', 'CO', 'RETAIL',
             'CONTRACTORS', 'SOLUTIONS', 'SYSTEMS', 'MANAGEMENT', 'ENTERPRISES', 'EUROPE', 'BRITISH'}


@dataclass
class DeepDive:
    sac: str
    customer: str
    period: str
    pnl: pd.DataFrame                 # fact_pnl rows (FY26 WD4 + FY25 24-month)
    product_summary: pd.DataFrame     # one row per product
    circuits: pd.DataFrame            # mapped circuits + P06 rates
    circuit_tie: pd.DataFrame         # per product: UKP cost vs circuit cost
    voice: pd.DataFrame               # voice inventory rows for the SAC
    voice_tie: pd.DataFrame
    mapping: pd.DataFrame             # Customer2SAC evidence
    findings: pd.DataFrame
    tracker: pd.DataFrame
    sources: pd.DataFrame
    checks: list = field(default_factory=list)
    headline: dict = field(default_factory=dict)


def _keywords(name: str) -> list[str]:
    words = re.findall(r"[A-Z0-9&']+", name.upper())
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS][:2]


def _name_pattern(names: list[str]) -> str:
    """Regex that matches a Customer2SAC name containing ALL of the first two distinctive words
    of any of the given customer names (avoids 'Example Group' for 'Example Holdings')."""
    alts = []
    for n in names:
        kw = _keywords(n or '')
        if kw:
            alts.append(''.join(rf'(?=.*\b{re.escape(k)}\b)' for k in kw))
    return '|'.join(f'(?:{a})' for a in dict.fromkeys(alts))


def run_deepdive(rep: SacReport | None, sac: str, pf: PeriodFiles, cfg: dict, recon=None) -> DeepDive:
    dc = cfg['deepdive']
    pcol = dc['product_column']
    P = pf.period or 'P06'
    checks, findings, sources = [], [], []

    def chk(check, ok, value='', detail='', area='Deep dive'):
        checks.append({'SAC': sac, 'Area': area, 'Check': check,
                       'Result': ok if isinstance(ok, str) else ('PASS' if ok else 'FAIL'), 'Value': value, 'Detail': detail})

    def src(item, key, tab, how):
        sources.append({'SAC': sac, 'Analysis item': item, 'Source file': pf.name(key), 'Tab': tab, 'How to reproduce': how})
        return f"{pf.name(key)} → {tab} → {how}"

    # ------------------------------------------------------------------ P&L
    wd4 = pf.wd4()
    cy = wd4[wd4['SAC'] == sac].copy()
    customer = (cy['SAC Name'].dropna().iloc[0] if len(cy) else '') or (rep.customer if rep else '')
    s_pnl = src('UKP P&L FY26 YTD (by product, period, entity, type)', 'wd4', 'Data',
                f'Filter SAC = {sac}; pivot Revenue / Cost / Margin by {pcol}, Period, Entity, Type')
    cy = cy.assign(FY='FY26', Product=cy[pcol].fillna('(blank)'))
    try:
        py_all = pf.m24('PY')
        py = py_all[py_all['SAC'] == sac].copy()
        py = py.assign(FY='FY25', Product=py[pcol].fillna('(blank)'))
        src('UKP P&L FY25 (prior year)', 'm24', 'PY-Data', f'Filter SAC = {sac}; SumOfRevenue / SumOfMargin by {pcol}, Period')
        cy24 = pf.m24('CY')
        cy24 = cy24[cy24['SAC'] == sac]
        a, b = round(cy['Revenue'].sum(), 2), round(cy24['Revenue'].sum(), 2)
        chk('WD4 FY26 revenue = 24-month CY-Data revenue', abs(a - b) < 1, a, f'24-month {b:,.2f}')
    except Exception as ex:  # 24-month report missing
        py = pd.DataFrame(columns=cy.columns)
        py_all = py
        chk('24-month report available', 'WARN', '', str(ex))
    cols = ['FY', 'Period', 'Entity', 'Type', 'Product', 'Revenue', 'Cost', 'Margin']
    pnl = pd.concat([cy[cols], py[cols]], ignore_index=True)
    pnl['Cost'] = pnl['Revenue'] - pnl['Margin']          # Cost always = Revenue - Margin
    pnl.insert(0, 'SAC', sac)
    pnl['Internal/External'] = pnl['Type']
    chk('FY26 Revenue - Cost = Margin (every row)', bool(np.allclose(cy['Revenue'] - cy['Cost'], cy['Margin'], atol=0.02)),
        len(cy))

    fy26 = pnl[pnl['FY'] == 'FY26']
    fy25 = pnl[pnl['FY'] == 'FY25']
    ps = (fy26.groupby('Product')[['Revenue', 'Cost', 'Margin']].sum()
          .join(fy25.groupby('Product')[['Revenue', 'Margin']].sum().add_prefix('FY25 '), how='outer').fillna(0))
    ext = fy26[fy26['Type'] == 'External'].groupby('Product')[['Revenue', 'Cost', 'Margin']].sum().add_prefix('External ')
    inn = fy26[fy26['Type'] == 'Internal'].groupby('Product')[['Revenue', 'Cost', 'Margin']].sum().add_prefix('Internal ')
    ps = ps.join(ext, how='left').join(inn, how='left').fillna(0).round(2)
    monthly = fy26.pivot_table(index='Product', columns='Period', values='Revenue', aggfunc='sum').reindex(columns=PERIODS).dropna(axis=1, how='all').fillna(0)
    mcost = fy26.pivot_table(index='Product', columns='Period', values='Cost', aggfunc='sum').reindex(columns=monthly.columns).fillna(0)
    periods_present = list(monthly.columns)

    # ------------------------------------------------------------------ circuits
    c2s = pf.circuit2sac()
    mapped = c2s[c2s['SAC'] == sac][['OR Circuit ID', 'Comments']].drop_duplicates('OR Circuit ID')
    s_circ = src('Circuits mapped to the SAC', 'mapping', 'OR_Circuit_ID2SAC Mapping',
                 f'Filter "SAC " (header has a trailing space) = {sac}')
    prod = pf.product_extract()
    rates = (prod.groupby(['OR_CIRCUIT_ID', 'Sheet'])
             .agg(Rate=('PRODUCT_RATE', 'sum'), Lines=('PRODUCT_RATE', 'size'),
                  Description=('PRODUCT_DESC', 'first'), Town=('POST_TOWN', 'first'),
                  Postcode=('POSTCODE_1', lambda s: ' / '.join(sorted(set(s.dropna().astype(str))))[:40]),
                  Address=('ADDRESS_1', 'first'), ExtractSAC=('SAC', 'first')).reset_index())
    circuits = mapped.merge(rates, left_on='OR Circuit ID', right_on='OR_CIRCUIT_ID', how='left')
    circuits['Status'] = np.where(circuits['Rate'].notna(), f'Live ({P} cost rows)', f'No {P} cost rows (presumed ceased)')
    circuits['Product'] = circuits['Sheet'].map(SHEET_TO_PRODUCT).fillna('')
    circuits['Rate'] = circuits['Rate'].round(2)
    circuits.insert(0, 'SAC', sac)
    circuits = circuits.drop(columns=['OR_CIRCUIT_ID'])
    s_rates = src(f'Circuit monthly rental ({P})', 'products', 'SHDS / IP / OPTICAL / ETHERNET / INTERNET CONNECT Data',
                  'Filter OR_CIRCUIT_ID to the mapped circuits; sum PRODUCT_RATE (START_DATE/END_DATE are Excel serial dates)')
    # circuits in the extract tagged to this SAC but missing from the mapping
    if 'SAC' in prod:
        extra = prod[(prod['SAC'] == sac) & ~prod['OR_CIRCUIT_ID'].isin(mapped['OR Circuit ID'])]['OR_CIRCUIT_ID'].nunique()
        chk('Product-extract circuits for this SAC are all in the circuit mapping', extra == 0, extra, area='Mapping')

    last = periods_present[-1] if periods_present else P
    tie_rows = []
    live = circuits[circuits['Rate'].notna()]
    for prodname, g in live.groupby('Product'):
        ukp = float(mcost.loc[prodname, last]) if prodname in mcost.index and last in mcost.columns else 0.0
        circ = float(g['Rate'].sum())
        gap = ukp - circ
        tie_rows.append({'SAC': sac, 'Product': prodname, 'Live circuits': len(g), f'Circuit rental ({P})': round(circ, 2),
                         f'UKP cost ({last})': round(ukp, 2), 'Unexplained cost': round(gap, 2),
                         'Tie-out': 'Ties' if abs(gap) <= dc['circuit_tolerance_gbp'] else 'Gap'})
    circuit_tie = pd.DataFrame(tie_rows)
    for r in tie_rows:
        chk(f"{r['Product']}: circuit rental ties to UKP {last} cost", 'PASS' if r['Tie-out'] == 'Ties' else 'WARN',
            r[f'Circuit rental ({P})'], f"UKP {r[f'UKP cost ({last})']:,.2f}; gap {r['Unexplained cost']:,.2f}")

    # ------------------------------------------------------------------ voice
    vo = pf.voice()
    v = vo[vo['SAC'] == sac].copy()
    s_voice = src(f'Voice inventory ({P})', 'voice', 'OAL (PSTN) / OAM (Featureline) / OAN (ISDN)',
                  f'Filter SAC = {sac}; sum Costs and Revenue; BILL_ACCOUNT = billing account')
    voice_tie = (v.groupby(['Tab', 'Description']).agg(Accounts=('BILL_ACCOUNT', 'nunique'), Lines=('Quantity', 'sum'),
                                                       Costs=('Costs', 'sum'), Revenue=('Revenue', 'sum')).reset_index()
                 if len(v) else pd.DataFrame(columns=['Tab', 'Description', 'Accounts', 'Lines', 'Costs', 'Revenue']))
    voice_tie.insert(0, 'SAC', sac)
    sac_accts = set(rep.ent['acct']) - {''} if rep is not None else set()
    v_in_rep = v['BILL_ACCOUNT'].isin(sac_accts).sum() if len(v) else 0
    elsewhere = vo[vo['BILL_ACCOUNT'].isin(sac_accts) & (vo['SAC'] != sac)]
    elsewhere_sum = (elsewhere.groupby('SAC').agg(Accounts=('BILL_ACCOUNT', 'nunique'), Costs=('Costs', 'sum'))
                     .reset_index() if len(elsewhere) else pd.DataFrame())
    voice_rows = v[['Tab', 'Description', 'BILL_ACCOUNT', 'Quantity', 'Costs', 'Revenue', 'CHARGEDESCRPTION']].copy() if len(v) else pd.DataFrame()
    if len(voice_rows):
        voice_rows.insert(0, 'SAC', sac)

    # ------------------------------------------------------------------ mapping
    c2c = pf.customer2sac()
    kws = _keywords(customer or (rep.customer if rep else ''))
    s_map = src('Customer-name mapping', 'mapping', 'Customer2SAC Mapping',
                f'Filter SAC = {sac}; then search Customer Name containing {" / ".join(kws) or "(name)"}')
    m_this = c2c[c2c['SAC'] == sac].assign(Evidence='Mapped to this SAC')
    patt = _name_pattern([customer, rep.customer if rep else ''])
    m_other = (c2c[c2c['Customer Name'].str.upper().str.contains(patt, regex=True) & (c2c['SAC'] != sac)]
               .assign(Evidence='Name matches customer but mapped to another SAC') if patt else c2c.iloc[0:0])
    mapping = pd.concat([m_this, m_other], ignore_index=True)
    les = sorted(set(rep.ent['Legal Entity Name']) - {''}) if rep is not None else []
    mapped_names = set(c2c['Customer Name'].str.upper())
    unmapped = [le for le in les if le.upper() not in mapped_names]
    if unmapped:
        mapping = pd.concat([mapping, pd.DataFrame({'Customer Name': unmapped, 'SAC': '',
                                                    'Evidence': 'Legal entity in SAC report with no Customer2SAC entry'})],
                            ignore_index=True)
    mapping.insert(0, 'SAC (investigated)', sac)
    def _clean(x):
        x = '' if x is None else str(x).strip()
        return '' if x.upper() in ('', '0', 'NULL', 'NAN', 'NONE', '#N/A', 'N/A') else x
    wk = cy['World Key'].map(_clean)
    wk = wk[wk != ''].iloc[0] if (wk != '').any() else ''
    if not wk:
        o = pf.sac_to_wk()
        o = o[o['Account Code'] == sac]
        wk = _clean(o['World Key'].iloc[0]) if len(o) else ''
    src('World Key', 'outlook', 'SAC to WK Mapping', f'Filter Account Code = {sac} (WD4 World Key column checked first)')

    # ------------------------------------------------------------------ rules -> findings
    has_circ = set(live['Product'])
    has_voice = {VOICE_TO_PRODUCT.get(d, d) for d in v['Description'].unique()} if len(v) else set()

    def add(product, flag, severity, impact, finding, action, issue_type, source, accounts='', circuits_=''):
        findings.append({'SAC': sac, 'Product': product, 'Flag': flag, 'Severity': severity,
                         'Impact £': round(float(impact), 2), 'Finding': finding, 'Action': action,
                         'Issue type': issue_type, 'Billing accounts': accounts, 'Circuit IDs': circuits_, 'Source': source})

    for prodname, r in ps.iterrows():
        rev, cost, mar = r['Revenue'], r['Cost'], r['Margin']
        series = monthly.loc[prodname] if prodname in monthly.index else pd.Series(dtype=float)
        cseries = mcost.loc[prodname] if prodname in mcost.index else pd.Series(dtype=float)
        inv = prodname in has_circ or prodname in has_voice or any(k in prodname for k in has_voice)
        circ_ids = ', '.join(live.loc[live['Product'] == prodname, 'OR Circuit ID'].head(8))
        # eliminations: external and internal cancel exactly
        if abs(rev) < 0.01 and abs(mar) < 0.01 and (r['External Revenue'] != 0):
            add(prodname, 'Elimination pair nets to zero', 'Info', 0,
                f'External {r["External Revenue"]:,.2f} and internal {r["Internal Revenue"]:,.2f} cancel exactly '
                f'(OneBill / contract elimination). Retail revenue correctly kept out of UKP.',
                'None — control only.', 'Control', s_pnl)
            continue
        nzp = [k for k, x in (series.abs() + cseries.abs()).items() if k in periods_present and abs(x) > 0.5]
        ended = (f' Activity stopped after {nzp[-1]}.' if nzp and nzp[-1] != periods_present[-1] else '')
        trend = ', '.join(f'{k} {x:,.0f}' for k, x in series.items() if k in periods_present and abs(x) > 0.5)
        if rev < -dc['materiality_gbp'] and not inv:
            add(prodname, 'Negative revenue, no inventory', 'High', rev,
                f'{prodname} books {rev:,.2f} revenue YTD ({mar:,.2f} margin) with no circuit or voice inventory under {sac}. '
                f'Same pattern as the Dorma precedent: credits landing in 503/UKP for a service billed elsewhere (820 GFR).' + ended
                + (f' Monthly revenue: {trend}.' if trend else ''),
                'Find the journal source of the credits and stop them booking to this SAC.', 'Unmapped revenue lines', s_pnl)
        elif cost > dc['materiality_gbp'] and abs(rev) < 0.05 * cost:
            add(prodname, 'Cost with no revenue', 'High', -cost,
                f'{prodname} carries {cost:,.2f} cost YTD and {rev:,.2f} revenue.' + ended
                + (f' {len(live[live["Product"] == prodname])} live circuits behind it.' if prodname in has_circ else ''),
                'Confirm whether the service is live: move revenue/cost into the same GFR, or cease the circuits.',
                'Cost leakage', s_pnl, circuits_=circ_ids)
        # revenue stopped while cost continues
        nz = series[series.index.isin(periods_present)]
        stopped = False
        if len(nz) >= 6:
            first, lastp = nz.iloc[:3].mean(), nz.iloc[-3:].mean()
            if first > 100 and lastp < dc['stop_share'] * first:
                stopped = True
                c_last = cseries.iloc[-3:].mean() if len(cseries) else 0
                verb = 'turned negative' if lastp < 0 else 'dropped'
                add(prodname, 'Revenue stopped' if lastp >= 0 else 'Revenue turned to credits',
                    'High' if (c_last > 100 or lastp < -100) else 'Medium', (lastp - first) * 3,
                    f'Revenue {verb}: {first:,.0f}/month in {nz.index[0]}–{nz.index[2]} vs {lastp:,.0f}/month in '
                    f'{nz.index[-3]}–{nz.index[-1]}' + (f'; cost still {c_last:,.0f}/month.' if c_last > 100 else '.'),
                    'Trace where the revenue is booking now (journal / SAP product mapping).', 'Revenue drop', s_pnl,
                    circuits_=circ_ids)
        # one-off swing: only the single largest period per product and measure, and only when it
        # is not already explained by a "revenue stopped" pattern
        for label, ser in (('revenue', series), ('cost', cseries)):
            ser = ser[ser.index.isin(periods_present)]
            if len(ser) < 3 or (label == 'revenue' and stopped):
                continue
            per = ser.abs().idxmax()
            val = ser[per]
            base = ser.drop(per).abs().median()
            if abs(val) > 1000 and abs(val) > dc['one_off_multiple'] * max(base, 1):
                add(prodname, f'One-off {label} entry', 'High' if abs(val) > 10000 else 'Medium',
                    val if label == 'revenue' else -val,
                    f'{prodname} {label} of {val:,.2f} in {per} against a typical {base:,.0f}/month '
                    f'(excess ≈ {abs(val) - base:,.0f}).',
                    f'Get the {per} journal behind this {label} entry (accrual release / true-up / reallocation?).',
                    'One-off entry', s_pnl)
        # cost entity switch
        ce = fy26[(fy26['Product'] == prodname)].pivot_table(index='Period', columns='Entity', values='Cost', aggfunc='sum').fillna(0)
        if ce.shape[1] >= 2 and len(ce) >= 4:
            dom = ce.abs().idxmax(axis=1)
            dom = dom[ce.abs().max(axis=1) > 500]
            if dom.nunique() >= 2 and (dom != dom.iloc[0]).any():
                sw = dom[dom != dom.iloc[0]].index[0]
                add(prodname, 'Cost moved to another BT entity', 'Medium', 0,
                    f'{prodname} cost was booked on entity {dom.iloc[0]} until {dom.index[dom.index.get_loc(sw) - 1]} '
                    f'and on {dom[sw]} from {sw}.', f'Get the {dom[sw]} cost journal from {sw} onwards.', 'Re-allocation', s_pnl)
        # circuit gap
        t = circuit_tie[circuit_tie['Product'] == prodname] if len(circuit_tie) else pd.DataFrame()
        if len(t) and t['Tie-out'].iloc[0] == 'Gap':
            gap = t['Unexplained cost'].iloc[0]
            add(prodname, 'Cost not explained by circuits', 'Medium', -gap,
                f'UKP {last} cost {t[f"UKP cost ({last})"].iloc[0]:,.2f} vs circuit rental {t[f"Circuit rental ({P})"].iloc[0]:,.2f}: '
                f'{gap:,.2f}/month has no circuit behind it in the {P} product extract.',
                'Find the cost lines without a mapped circuit.', 'Unexplained cost', s_rates, circuits_=circ_ids)
        elif len(t):
            add(prodname, 'Circuit cost ties to UKP', 'Info', 0,
                f'{t["Live circuits"].iloc[0]} live circuits = {t[f"Circuit rental ({P})"].iloc[0]:,.2f}/month, matching UKP {last} cost.',
                'Evidence only.', 'Control', s_rates, circuits_=circ_ids)

    # mirror SAC: entries with an exact opposite on another SAC (same product & period)
    for fy, mine, allrows in (('FY26', cy, wd4), ('FY25', py, py_all)):
        big = mine[mine['Revenue'].abs() > 1000]
        if not len(big):
            continue
        oth = allrows[(allrows['SAC'] != sac) & allrows['Period'].isin(big['Period'])][['SAC', 'Period', pcol, 'Revenue']]
        oth = oth.assign(key=oth['Period'] + '|' + oth[pcol].astype(str) + '|' + (-oth['Revenue']).round(2).astype(str))
        bk = big['Period'] + '|' + big[pcol].astype(str) + '|' + big['Revenue'].round(2).astype(str)
        hits = oth[oth['key'].isin(set(bk))]
        for msac, g in hits.groupby('SAC'):
            mv = big[bk.isin(set(g['Period'] + '|' + g[pcol].astype(str) + '|' + (-g['Revenue']).round(2).astype(str)))]
            add(g[pcol].iloc[0], 'Mirror entries on another SAC', 'Medium', 0,
                f'{fy}: {len(g)} entries on {sac} have an exact opposite on SAC {msac} (transfers between SACs), e.g. ' +
                ', '.join(f'{p} {v:,.2f}' for p, v in mv[['Period', 'Revenue']].head(3).values) + '.',
                f'Decide which SAC owns the contract ({sac} or {msac}).', 'Transfer between SACs', s_pnl)

    ceased = circuits[circuits['Rate'].isna()]
    if len(ceased):
        add('(mapping)', 'Mapped circuits with no cost', 'Low', 0,
            f'{len(ceased)} of {len(circuits)} circuits mapped to {sac} have no {P} cost rows (presumed ceased).',
            'Confirm and remove them from the circuit mapping.', 'Housekeeping', s_circ,
            circuits_=', '.join(ceased['OR Circuit ID'].head(10)))
    if len(m_other):
        add('(mapping)', 'Customer name mapped to another SAC', 'High' if len(m_this) == 0 else 'Medium', 0,
            'Names matching the customer map elsewhere: ' + '; '.join(f'"{a}" → {b}' for a, b in
                                                                     m_other[['Customer Name', 'SAC']].head(6).values),
            'Correct or confirm these Customer2SAC entries.', 'Mapping', s_map)
    if unmapped:
        add('(mapping)', 'Legal entities not mapped', 'Low', 0,
            f'{len(unmapped)} legal entities in the SAC report have no Customer2SAC entry: ' + '; '.join(unmapped[:6]),
            'Add them to Customer2SAC.', 'Mapping', s_map)
    if not wk:
        add('(mapping)', 'No World Key', 'Low', 0, f'{sac} has no World Key in UKP or the outlook mapping.',
            'Request a World Key.', 'Mapping', src('World Key check', 'wd4', 'Data', 'World Key column'))
    if len(elsewhere_sum):
        add('(voice)', 'Customer lines costed under another SAC', 'Medium', 0,
            f'{len(elsewhere)} voice rows for this customer\'s billing accounts sit under other SACs: ' +
            ', '.join(f'{a} ({b} accts)' for a, b in elsewhere_sum[['SAC', 'Accounts']].values[:5]),
            'Check those SAC assignments.', 'Mapping', s_voice)
    if len(cy) == 0:
        add('(all)', 'SAC not in UKP', 'Info', 0, f'{sac} has no rows in the {P} WD4 report.',
            'Confirm the estate is retail-billed (820 GFR) and absence from UKP is correct.', 'Control', s_pnl)

    findings = pd.DataFrame(findings, columns=['SAC', 'Product', 'Flag', 'Severity', 'Impact £', 'Finding', 'Action',
                                               'Issue type', 'Billing accounts', 'Circuit IDs', 'Source'])
    sev = {'High': 0, 'Medium': 1, 'Low': 2, 'Info': 3}
    findings = findings.sort_values(['Severity', 'Impact £'], key=lambda s: s.map(sev) if s.name == 'Severity' else s.abs() * -1)

    # ------------------------------------------------------------------ tracker rows (one per product)
    tr = []
    for prodname, r in ps.iterrows():
        f = findings[findings['Product'] == prodname]
        main = f[f['Severity'] != 'Info']
        tr.append({'Resource Name': '', 'Contract Name': customer, 'SAC code': sac, 'Product': prodname,
                   'Issue type': main['Issue type'].iloc[0] if len(main) else '',
                   'Findings': ' | '.join(f['Finding']) if len(f) else 'No exception found by the rules.',
                   'Billing account': ', '.join(f['Billing accounts'].replace('', np.nan).dropna()),
                   'Circuit ID': ', '.join(f['Circuit IDs'].replace('', np.nan).dropna().head(1)),
                   'Impacted Revenue': round(float(main['Impact £'].sum()), 2) if len(main) else None,
                   'Action Log': ' | '.join(main['Action'].drop_duplicates()) if len(main) else '',
                   f'{P}(YTD) Revenue': r['Revenue'], f'{P}(YTD) Margin': r['Margin'],
                   'FY25 Revenue Reported': r['FY25 Revenue'], 'FY25 Margin Reported': r['FY25 Margin'],
                   'Comment': 'Source: ' + s_pnl})
    for _, f in findings[findings['Product'].str.startswith('(')].iterrows():
        tr.append({'Resource Name': '', 'Contract Name': customer, 'SAC code': sac, 'Product': f['Product'],
                   'Issue type': f['Issue type'], 'Findings': f['Finding'], 'Billing account': f['Billing accounts'],
                   'Circuit ID': f['Circuit IDs'], 'Impacted Revenue': None, 'Action Log': f['Action'],
                   f'{P}(YTD) Revenue': 0.0, f'{P}(YTD) Margin': 0.0, 'FY25 Revenue Reported': 0.0,
                   'FY25 Margin Reported': 0.0, 'Comment': 'Source: ' + f['Source']})
    tracker = pd.DataFrame(tr)
    tot_rev, tot_mar = round(float(fy26['Revenue'].sum()), 2), round(float(fy26['Margin'].sum()), 2)
    if len(tracker):
        chk('Tracker rows add up to FY26 YTD revenue', abs(tracker[f'{P}(YTD) Revenue'].sum() - tot_rev) < 0.05, tot_rev)
        chk('Tracker rows add up to FY26 YTD margin', abs(tracker[f'{P}(YTD) Margin'].sum() - tot_mar) < 0.05, tot_mar)
        chk('Tracker rows add up to FY25 revenue', abs(tracker['FY25 Revenue Reported'].sum() - fy25['Revenue'].sum()) < 0.05,
            round(float(fy25['Revenue'].sum()), 2))

    ps = ps.reset_index().rename(columns={'index': 'Product'})
    ps.insert(0, 'SAC', sac)
    headline = {'SAC': sac, 'Customer': customer, 'World Key': wk, 'Period': P,
                'FY26 YTD Revenue': tot_rev, 'FY26 YTD Cost': round(float(fy26['Cost'].sum()), 2), 'FY26 YTD Margin': tot_mar,
                'FY25 Revenue': round(float(fy25['Revenue'].sum()), 2), 'FY25 Margin': round(float(fy25['Margin'].sum()), 2),
                'Mapped circuits': len(circuits), 'Live circuits': len(live),
                f'Circuit rental {P}': round(float(live['Rate'].sum()), 2),
                'Voice accounts': int(v['BILL_ACCOUNT'].nunique()) if len(v) else 0,
                'Voice accounts in SAC report': int(v.loc[v['BILL_ACCOUNT'].isin(sac_accts), 'BILL_ACCOUNT'].nunique()) if len(v) else 0,
                'High findings': int((findings['Severity'] == 'High').sum()),
                '£ at stake': round(float(findings.loc[findings['Severity'].isin(['High', 'Medium']), 'Impact £'].abs().sum()), 2)}
    srcs = pd.DataFrame(sources).drop_duplicates()
    return DeepDive(sac, customer, P, pnl.round(2), ps, circuits, circuit_tie, voice_rows, voice_tie, mapping,
                    findings, tracker, srcs, checks, headline)

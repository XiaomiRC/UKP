"""File loaders for SAC reports, OneBill CSVs and the P06/P03 Marginbase/UKP .xlsb set.

Large .xlsb sheets are parsed once with pyxlsb and cached as parquet under .cache/
(keyed by file name + size + mtime), so later runs take seconds.
"""
from __future__ import annotations

import glob
import hashlib
import os
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get('UKP_CACHE', os.path.join(ROOT, '.cache'))
BILL_TOTAL = 'Total charges before VAT  (£)'
VP_RE = re.compile(r'VP\d{8}')


# --------------------------------------------------------------------------- xlsb + cache
def _cache_path(path: str, sheet: str) -> str:
    st = os.stat(path)
    key = f'{os.path.realpath(path)}|{sheet}|{st.st_size}|{st.st_mtime_ns}'
    return os.path.join(CACHE, hashlib.md5(key.encode()).hexdigest() + '.parquet')


_MEMORY_SHEETS = {}


def read_xlsb(path: str, sheet: str) -> pd.DataFrame:
    """Read one sheet of an .xlsb (header = first row), cached as parquet."""
    os.makedirs(CACHE, exist_ok=True)
    cp = _cache_path(path, sheet)
    if os.environ.get('UKP_MEMORY_ONLY') == '1':
        if cp in _MEMORY_SHEETS:
            return _MEMORY_SHEETS[cp].copy()
        print(f'Parsing {os.path.basename(path)} / {sheet}', flush=True)
        memory_key = cp
        cp = None
    if cp and os.path.exists(cp):
        return pd.read_parquet(cp)
    from pyxlsb import open_workbook
    with open_workbook(path) as wb:
        with wb.get_sheet(sheet) as sh:
            it = sh.rows(sparse=False)
            header = [c.v for c in next(it)]
            n = len(header)
            while n and header[n - 1] is None:
                n -= 1
            rows = []
            for row in it:
                values = [c.v for c in row][:n]
                if any(v is not None for v in values):
                    rows.append((values + [None] * n)[:n])
    n = len(header)
    while n and header[n - 1] is None:
        n -= 1
    header = [str(h).strip() if h is not None else f'col{i}' for i, h in enumerate(header[:n])]
    # de-duplicate header names (e.g. two 'SAC' columns in the product extract)
    seen = {}
    for i, h in enumerate(header):
        if h in seen:
            seen[h] += 1
            header[i] = f'{h}.{seen[h]}'
        else:
            seen[h] = 0
    df = pd.DataFrame(rows, columns=header)
    # parquet needs consistent column types: keep numeric columns numeric, the rest as string
    for c in df.columns:
        s = df[c]
        num = pd.to_numeric(s, errors='coerce')
        if num.notna().sum() == s.notna().sum():
            df[c] = num
        else:
            df[c] = s.map(lambda v: None if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)))
    if cp:
        df.to_parquet(cp, index=False)
    else:
        _MEMORY_SHEETS[memory_key] = df.copy()
    return df


def norm_sac(s: pd.Series) -> pd.Series:
    """SAC codes come as text or numbers ('4813', 4813.0): normalise to stripped text."""
    return s.map(lambda v: '' if v is None or (isinstance(v, float) and np.isnan(v)) else
                 (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))).str.strip().str.upper()


# --------------------------------------------------------------------------- P06 file set
@dataclass
class PeriodFiles:
    folder: str
    period: str = ''
    files: dict = field(default_factory=dict)

    @classmethod
    def discover(cls, folder: str) -> 'PeriodFiles':
        pf = cls(folder)
        pats = {
            'mapping': '*Circuit - Customer - SAC mapping*.xlsb',
            'products': '*Products Data Extract*.xlsb',
            'voice': '*Voice Products Data Extract*.xlsb',
            'wd4': '*For SAP WD4*.xlsb',
            'm24': '*24 Month*.xlsb',
            'revenue': '*Products Revenue Report*.xlsb',
            'outlook': '*PL Outlook*.xlsb',
            'btb': '*BTB Trade Collapse*.xlsb',
        }
        for k, p in pats.items():
            hits = sorted(glob.glob(os.path.join(folder, p)))
            if k == 'products':
                hits = [h for h in hits if 'Voice' not in os.path.basename(h)]
            if hits:
                pf.files[k] = hits[0]
        m = re.search(r'P(\d{2})[-_]2026', ' '.join(os.path.basename(v) for v in pf.files.values()))
        pf.period = f'P{m.group(1)}' if m else ''
        return pf

    def name(self, key: str) -> str:
        return os.path.basename(self.files.get(key, '')) or f'({key} file not supplied)'

    # ---- sheets
    def wd4(self) -> pd.DataFrame:
        d = read_xlsb(self.files['wd4'], 'Data')
        d['SAC'] = norm_sac(d['SAC'])
        for c in ('Revenue', 'Margin', 'Cost'):
            d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0.0)
        return d

    def m24(self, which: str) -> pd.DataFrame:
        d = read_xlsb(self.files['m24'], f'{which}-Data')
        d['SAC'] = norm_sac(d['SAC'])
        d['Revenue'] = pd.to_numeric(d['SumOfRevenue'], errors='coerce').fillna(0.0)
        d['Margin'] = pd.to_numeric(d['SumOfMargin'], errors='coerce').fillna(0.0)
        d['Cost'] = d['Revenue'] - d['Margin']
        return d

    def customer2sac(self) -> pd.DataFrame:
        d = read_xlsb(self.files['mapping'], 'Customer2SAC Mapping')
        d['SAC'] = norm_sac(d['SAC'])
        d['Customer Name'] = d['Customer Name'].fillna('').astype(str).str.strip()
        return d

    def circuit2sac(self) -> pd.DataFrame:
        d = read_xlsb(self.files['mapping'], 'OR_Circuit_ID2SAC Mapping')
        d = d.rename(columns={c: c.strip() for c in d.columns})   # 'SAC ' has a trailing space
        d['SAC'] = norm_sac(d['SAC'])
        d['OR Circuit ID'] = d['OR Circuit ID'].fillna('').astype(str).str.strip().str.upper()
        return d

    PRODUCT_SHEETS = ['SHDS Data', 'IP CONNECT Data', 'OPTICAL CONNECT Data',
                      'ETHERNET CONNECT Data', 'INTERNET CONNECT Data']

    def product_extract(self) -> pd.DataFrame:
        keep = ['RECORDTYPE', 'PRODUCT_DESC', 'OR_CIRCUIT_ID', 'CHARGE_DESC', 'START_DATE', 'END_DATE',
                'QUANTITY', 'UNIT_RATE', 'PRODUCT_RATE', 'ADDRESS_1', 'ADDRESS_2', 'ADDRESS_3', 'POST_TOWN',
                'POSTCODE_1', 'POSTCODE_2', 'ACCT_INVOICE', 'CUST_ACCOUNT_NAME', 'SAC', 'SAC Name']
        out = []
        for s in self.PRODUCT_SHEETS:
            d = read_xlsb(self.files['products'], s)
            d = d[[c for c in keep if c in d.columns]].copy()
            d['Sheet'] = s
            out.append(d)
        d = pd.concat(out, ignore_index=True)
        d['OR_CIRCUIT_ID'] = d['OR_CIRCUIT_ID'].fillna('').astype(str).str.strip().str.upper()
        d['PRODUCT_RATE'] = pd.to_numeric(d['PRODUCT_RATE'], errors='coerce').fillna(0.0)
        if 'SAC' in d:
            d['SAC'] = norm_sac(d['SAC'])
        return d

    VOICE_TABS = ['OAL', 'OAM', 'OAN']

    def voice(self) -> pd.DataFrame:
        from pyxlsb import open_workbook
        with open_workbook(self.files['voice']) as wb:
            sheets = wb.sheets
        out = []
        for s in sheets:
            tab = s.split()[-1]
            if tab not in self.VOICE_TABS:
                continue
            d = read_xlsb(self.files['voice'], s)
            d['Tab'] = tab
            out.append(d)
        d = pd.concat(out, ignore_index=True)
        d['SAC'] = norm_sac(d['SAC'])
        d['BILL_ACCOUNT'] = d['BILL_ACCOUNT'].fillna('').astype(str).str.strip().str.upper()
        for c in ('Costs', 'Revenue', 'Quantity'):
            d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0.0)
        return d

    def sac_to_wk(self) -> pd.DataFrame:
        if 'outlook' not in self.files:
            return pd.DataFrame(columns=['Account Code', 'World Key'])
        d = read_xlsb(self.files['outlook'], 'SAC to WK Mapping')
        d['Account Code'] = norm_sac(d['Account Code'])
        return d


def parse_dates(s) -> pd.Series:
    """SAC report dates arrive as ISO strings (some with timezone) or dd/mm/yyyy: return tz-naive dates."""
    if s is None:
        return pd.Series(dtype='datetime64[ns]')
    s = pd.Series(s).fillna('').astype(str).str.strip()
    iso = pd.to_datetime(s.str.slice(0, 10), format='%Y-%m-%d', errors='coerce')
    uk = pd.to_datetime(s, format='%d/%m/%Y', errors='coerce')
    return iso.fillna(uk)


# --------------------------------------------------------------------------- SAC 360 report
@dataclass
class SacReport:
    path: str
    sac: str
    customer: str
    ent: pd.DataFrame
    onebills: pd.DataFrame        # OneBill, Status, BillType, Name, raw
    global_services: pd.DataFrame


def _onebill_tab(xl: pd.ExcelFile) -> pd.DataFrame:
    """The Onebill(s) tab is free-form (sometimes with headers, sometimes without):
    find every VPnnnnnnnn and treat the remaining cells on the row as its status text."""
    names = [n for n in xl.sheet_names if 'onebill' in n.lower()]
    rows = []
    if names:
        raw = pd.read_excel(xl, sheet_name=names[0], header=None, dtype=str)
        for r in raw.fillna('').itertuples(index=False):
            cells = [str(c).strip() for c in r]
            vps = [c for c in cells if VP_RE.fullmatch(c)]
            if not vps:
                continue
            rest = [c for c in cells if c and c not in vps]
            text = ' | '.join(rest)
            low = text.lower()
            if 'dedicated' in low:
                btype = 'Dedicated'
            elif 'bulk' in low or 'msfbt' in low:
                btype = 'Bulk'
            else:
                btype = ''
            if 'no result' in low or 'not found' in low:
                status = 'Not found'
            elif 'not active' in low or 'inactive' in low:
                status = 'Inactive'
            elif 'no bills' in low:
                status = 'Active, no bills'
            elif 'active' in low:
                status = 'Active'
            else:
                status = ''
            name = rest[-1] if len(rest) >= 3 else ''
            rows.append({'OneBill': vps[0], 'Status': status, 'BillType': btype, 'Name': name, 'Raw': text})
    return pd.DataFrame(rows, columns=['OneBill', 'Status', 'BillType', 'Name', 'Raw']).drop_duplicates('OneBill')


def load_sac_report(path: str) -> SacReport:
    xl = pd.ExcelFile(path)
    ent = pd.read_excel(xl, sheet_name='Enterprise', dtype=str)
    ent.columns = [str(c).strip() for c in ent.columns]
    for c in ('Billing Account Number', 'OneBill Account Number', 'Telephone Number', 'Service ID',
              'Billing System', 'Sub Sector', 'Legal Entity Name', 'Product Name', 'SAC Code', 'SAC Name'):
        if c not in ent:
            ent[c] = ''
        ent[c] = ent[c].fillna('').astype(str).str.strip()
    ent['acct'] = ent['Billing Account Number'].str.upper()
    ent['DP'] = pd.to_numeric(ent['Discounted Price'], errors='coerce').fillna(0.0)
    ent['ContractEnd'] = parse_dates(ent.get('Contract End Date'))
    gs = pd.read_excel(xl, sheet_name='Global Services', dtype=str) if 'Global Services' in xl.sheet_names else pd.DataFrame()
    sac = ent['SAC Code'].replace('', np.nan).dropna()
    sac = sac.mode().iloc[0].upper() if len(sac) else os.path.basename(path).split('_')[0].rstrip('-')
    cust = ent['SAC Name'].replace('', np.nan).dropna()
    cust = cust.mode().iloc[0] if len(cust) else ''
    return SacReport(path, sac, cust, ent, _onebill_tab(xl), gs)


# --------------------------------------------------------------------------- OneBill CSVs
@dataclass
class BillFile:
    path: str
    file_vp: str            # VP number in the file name
    rows_vp: str            # VP number in the Account column ('' if empty file)
    bill_date: str          # date in the file name
    df: pd.DataFrame        # lines (Total row removed)
    total_row: float | None


def load_bill(path: str) -> BillFile:
    base = os.path.basename(path)
    m = VP_RE.search(base)
    file_vp = m.group(0) if m else ''
    dm = re.search(r'(\d{2}-[A-Za-z]{3}-\d{2})', base)
    bill_date = dm.group(1) if dm else ''
    if os.path.getsize(path) == 0:
        return BillFile(path, file_vp, '', bill_date, pd.DataFrame(), None)
    d = pd.read_csv(path, encoding='latin1', dtype=str)
    d.columns = [c.strip().replace('\xa3', '£').replace('�', '£') for c in d.columns]
    tot_col = [c for c in d.columns if c.startswith('Total charges before VAT')][0]
    d = d.rename(columns={tot_col: BILL_TOTAL})
    is_total = d['Service number'].fillna('').str.strip().str.lower() == 'total'
    total_row = pd.to_numeric(d.loc[is_total, BILL_TOTAL].str.replace(',', ''), errors='coerce').sum() if is_total.any() else None
    d = d[~is_total].copy()
    money = [c for c in d.columns if '(£)' in c]
    for c in money:
        d[c] = pd.to_numeric(d[c].fillna('').str.replace(',', ''), errors='coerce').fillna(0.0)
    d['svc'] = d['Service number'].fillna('').str.replace("'", '').str.strip().str.upper()
    d['svc_base'] = d['svc'].str.split('/').str[0]
    d['src'] = d['Source account'].fillna('').str.strip().str.upper()
    d['OneBill'] = d['Account'].fillna('').str.strip()
    d['stype'] = d['Service type'].fillna('').str.strip()
    d['acctkey'] = np.where(d['src'] != '', d['src'], d['svc'])
    d['rent_start'] = pd.to_datetime(d.get('Rental start date', '').str.strip(), errors='coerce', dayfirst=True)
    d['rent_end'] = pd.to_datetime(d.get('Rental end date', '').str.strip(), errors='coerce', dayfirst=True)
    d['rent_days'] = pd.to_numeric(d.get('Rental days'), errors='coerce')
    d['file'] = base
    rows_vp = d['OneBill'].replace('', np.nan).dropna()
    rows_vp = rows_vp.mode().iloc[0] if len(rows_vp) else ''
    return BillFile(path, file_vp, rows_vp, bill_date, d, total_row)

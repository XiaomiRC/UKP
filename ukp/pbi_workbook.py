"""Pack dataset/*.csv into one Excel workbook (one Excel Table per sheet) for Power BI online upload."""
import glob
import os
import sys

import pandas as pd
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {'fact_recon_service', 'fact_sources'}   # large detail tables not used by the online report


def main(out=None):
    out = out or os.path.join(ROOT, 'dataset', 'UKP_Dataset.xlsx')
    wb = Workbook()
    wb.remove(wb.active)
    for path in sorted(glob.glob(os.path.join(ROOT, 'dataset', '*.csv'))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name in SKIP:
            continue
        d = pd.read_csv(path, dtype={'SAC': str, 'World Key': str, 'Billing accounts': str, 'AI chat value': str, 'App value': str})
        ws = wb.create_sheet(name[:31])
        ws.append(list(d.columns))
        for row in d.itertuples(index=False):
            ws.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in row])
        ref = f'A1:{get_column_letter(len(d.columns))}{max(len(d) + 1, 2)}'
        t = Table(displayName=name, ref=ref)
        t.tableStyleInfo = TableStyleInfo(name='TableStyleLight9', showRowStripes=True)
        ws.add_table(t)
    wb.save(out)
    print('wrote', out)


if __name__ == '__main__':
    main(*sys.argv[1:])

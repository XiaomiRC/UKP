"""UKP SAC Investigator — command line entry point (pure rule-based logic, no AI).

Examples
  python run.py --sac 941BS                 # reconciliation + P06 deep-dive for one SAC
  python run.py --all                       # every SAC report in inputs/sac_reports
  python run.py --sac TEST02 --recon-only    # only the SAC vs OneBill reconciliation
  python run.py --sac X6510 --period inputs/P03

Inputs (defaults):  inputs/sac_reports/<SAC>_*.xlsx,  inputs/bills/VP*.csv,  inputs/P06/*.xlsb
Outputs:            outputs/<SAC>/*.xlsx   and   dataset/*.csv  (Power BI reads this folder)
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time

import yaml

from ukp.deepdive import run_deepdive
from ukp.export import write_dataset, write_deepdive, write_reconciliation, write_tracker
from ukp.loaders import VP_RE, PeriodFiles, load_bill, load_sac_report
from ukp.reconcile import reconcile

ROOT = os.path.dirname(os.path.abspath(__file__))


def find_sac_report(folder: str, sac: str) -> str | None:
    hits = [f for f in glob.glob(os.path.join(folder, '*.xlsx'))
            if os.path.basename(f).upper().split('_')[0].rstrip('-') == sac.upper()]
    return sorted(hits)[-1] if hits else None


def pick_bills(rep, bill_dir: str) -> list[str]:
    """Bills whose VP number the SAC report references (Onebill tab or Enterprise 'OneBill Account Number')."""
    refs = set(rep.onebills['OneBill']) if len(rep.onebills) else set()
    refs |= set(rep.ent['OneBill Account Number'].str.split(',').explode().str.strip()) - {''}
    out = []
    for f in sorted(glob.glob(os.path.join(bill_dir, '*.csv'))):
        m = VP_RE.search(os.path.basename(f))
        if m and m.group(0) in refs:
            out.append(f)
    return out


def run_one(sac: str, a, cfg, pf) -> dict:
    t0 = time.time()
    out_dir = os.path.join(a.out, sac)
    os.makedirs(out_dir, exist_ok=True)
    rpath = find_sac_report(a.sac_reports, sac)
    rep = load_sac_report(rpath) if rpath else None
    recon = dd = None
    files = []
    if rep is not None and not a.deepdive_only:
        bills = pick_bills(rep, a.bills)
        recon = reconcile(rep, [load_bill(b) for b in bills], cfg)
        files.append(write_reconciliation(recon, out_dir))
    elif rep is None:
        print(f'  ! no SAC report found for {sac} in {a.sac_reports} — reconciliation skipped')
    if pf is not None and not a.recon_only:
        dd = run_deepdive(rep, sac, pf, cfg, recon)
        files.append(write_deepdive(dd, out_dir, recon))
        files.append(write_tracker(dd, out_dir))
    write_dataset(a.dataset, sac, recon, dd, {'Run at': time.strftime('%Y-%m-%d %H:%M'),
                                               'SAC report file': os.path.basename(rpath) if rpath else '',
                                               'Period files': pf.period if pf else ''})
    checks = (recon.checks if recon else []) + (dd.checks if dd else [])
    fails = sum(c['Result'] == 'FAIL' for c in checks)
    warns = sum(c['Result'] == 'WARN' for c in checks)
    print(f'  {sac}: {len(files)} files, {len(checks)} checks ({fails} FAIL, {warns} WARN) in {time.time() - t0:.1f}s')
    for f in files:
        print('     ', os.path.relpath(f, ROOT))
    return {'sac': sac, 'recon': recon, 'dd': dd}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--sac', nargs='*', default=[], help='SAC code(s)')
    p.add_argument('--all', action='store_true', help='run every SAC report in --sac-reports')
    p.add_argument('--sac-reports', default=os.path.join(ROOT, 'inputs', 'sac_reports'))
    p.add_argument('--bills', default=os.path.join(ROOT, 'inputs', 'bills'))
    p.add_argument('--period', default=os.path.join(ROOT, 'inputs', 'P06'), help='folder with the period .xlsb set')
    p.add_argument('--out', default=os.path.join(ROOT, 'outputs'))
    p.add_argument('--dataset', default=os.path.join(ROOT, 'dataset'))
    p.add_argument('--config', default=os.path.join(ROOT, 'config', 'rules.yaml'))
    modes = p.add_mutually_exclusive_group()
    modes.add_argument('--recon-only', action='store_true')
    modes.add_argument('--deepdive-only', action='store_true')
    a = p.parse_args(argv)
    cfg = yaml.safe_load(open(a.config, encoding='utf-8'))
    sacs = [s.upper() for s in a.sac]
    if a.all:
        sacs += sorted({os.path.basename(f).upper().split('_')[0].rstrip('-')
                        for f in glob.glob(os.path.join(a.sac_reports, '*.xlsx'))})
    if not sacs:
        p.error('give --sac CODE or --all')
    pf = None
    if not a.recon_only:
        pf = PeriodFiles.discover(a.period)
        missing = [k for k in ('wd4', 'mapping', 'products', 'voice') if k not in pf.files]
        if missing:
            p.error(f'period folder missing required inputs: {", ".join(missing)}')
        else:
            cache_note = 'temporary browser memory only' if os.environ.get('UKP_MEMORY_ONLY') == '1' else 'first run parses .xlsb; later runs use .cache'
            print(f'Period files: {pf.period} ({cache_note})')
    for sac in sacs:
        if not find_sac_report(a.sac_reports, sac):
            p.error(f'No SAC report found for {sac}')
    results = [run_one(s, a, cfg, pf) for s in dict.fromkeys(sacs)]
    print(f'Done. Power BI dataset: {os.path.relpath(a.dataset, ROOT)}/ — refresh the report to see the new data.')
    return results


if __name__ == '__main__':
    sys.exit(0 if main() else 1)

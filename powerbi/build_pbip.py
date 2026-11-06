"""Generate the Power BI Project (PBIP: TMDL semantic model + report) from the CSVs in dataset/.

Run after the dataset exists:   python powerbi/build_pbip.py
Then on Windows open powerbi/UKP_Dashboard.pbip in Power BI Desktop, set the DatasetFolder parameter
(Transform data -> Edit parameters) to the full path of the dataset folder, ending with a backslash, and Refresh.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import uuid

import pandas as pd

try:
    from to_pbir import report_parts
except ImportError:  # imported as powerbi.build_pbip
    from powerbi.to_pbir import report_parts

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DS = os.path.join(ROOT, 'dataset')
NAME = 'UKP_Dashboard'
NS = uuid.UUID('6f1c1d9e-2a7b-4c55-9d3e-0b1f2a3c4d5e')
NUMERIC_HINT = re.compile(r'Revenue|Cost|Margin|Amount|Rate|rental|GBP|Difference|count|circuits|accounts|Lines|Rows|'
                          r'findings|total|Chase|matched|Impact|Unexplained|Order', re.I)
FORCE_TEXT = {'SAC', 'World Key', 'Billing accounts', 'Billing Account', 'OneBill', 'Value', 'AI chat value',
              'App value', 'Service Number', 'Source Account', 'SAC Billing Account', 'OR Circuit ID', 'Period'}


def tag(*parts) -> str:
    return str(uuid.uuid5(NS, '|'.join(parts)))


def q(name: str) -> str:
    return name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) else "'" + name.replace("'", "''") + "'"


def col_types(path: str) -> list[tuple[str, str]]:
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    out = []
    for c in d.columns:
        vals = d[c][d[c] != '']
        num = pd.to_numeric(vals, errors='coerce')
        is_num = c not in FORCE_TEXT and NUMERIC_HINT.search(c) and len(vals) and num.notna().all()
        if is_num:
            out.append((c, 'int64' if (num % 1 == 0).all() and not re.search(r'Revenue|Cost|Margin|Amount|GBP|rental|Rate|Impact|Difference|total|Unexplained', c, re.I) else 'double'))
        else:
            out.append((c, 'string'))
    return out


# --------------------------------------------------------------------------- measures per table
MEASURES = {
    'dim_sac': [
        ('SACs', 'DISTINCTCOUNT(dim_sac[SAC])', '0'),
        ('YTD Revenue', "SUM(dim_sac[FY26 YTD Revenue])", '#,##0'),
        ('YTD Cost', "SUM(dim_sac[FY26 YTD Cost])", '#,##0'),
        ('YTD Margin', "SUM(dim_sac[FY26 YTD Margin])", '#,##0'),
        ('Margin %', 'DIVIDE([YTD Margin], [YTD Revenue])', '0.0%'),
        ('FY25 Margin Total', "SUM(dim_sac[FY25 Margin])", '#,##0'),
        ('Total GBP At Stake', "SUM(dim_sac[GBP at stake])", '#,##0'),
        ('Total High Findings', "SUM(dim_sac[High findings])", '0'),
        ('Live Circuit Rental', "SUM(dim_sac[Circuit rental])", '#,##0.00'),
        ('Accounts In Both', "SUM(dim_sac[In Both (count)])", '#,##0'),
        ('Accounts SAC Only', "SUM(dim_sac[In SAC only (count)])", '#,##0'),
        ('Accounts OneBill Only', "SUM(dim_sac[In OneBill only (count)])", '#,##0'),
        ('Accounts To Chase', "SUM(dim_sac[Chase items])", '#,##0'),
    ],
    'fact_recon_account': [
        ('Accounts', 'COUNTROWS(fact_recon_account)', '#,##0'),
        ('Match Rate %', 'DIVIDE(CALCULATE([Accounts], fact_recon_account[Status] = "In Both"), [Accounts])', '0.0%'),
        ('SAC GBP', "SUM(fact_recon_account[SAC Amount])", '#,##0.00'),
        ('Bill GBP', "SUM(fact_recon_account[OneBill Amount])", '#,##0.00'),
    ],
    'fact_pnl': [
        ('Total Revenue', 'SUM(fact_pnl[Revenue])', '#,##0'),
        ('Total Cost', 'SUM(fact_pnl[Cost])', '#,##0'),
        ('Total Margin', 'SUM(fact_pnl[Margin])', '#,##0'),
    ],
    'fact_findings': [
        ('Findings', 'COUNTROWS(fact_findings)', '0'),
        ('Findings Impact GBP', 'SUM(fact_findings[Impact GBP])', '#,##0'),
    ],
    'fact_checks': [
        ('Checks', 'COUNTROWS(fact_checks)', '0'),
        ('Checks Passed %', 'DIVIDE(CALCULATE(COUNTROWS(fact_checks), fact_checks[Result] = "PASS"), '
                            'CALCULATE(COUNTROWS(fact_checks), fact_checks[Result] IN {"PASS", "FAIL", "WARN"}))', '0.0%'),
        ('Checks Failed', 'CALCULATE(COUNTROWS(fact_checks), fact_checks[Result] = "FAIL") + 0', '0'),
    ],
    'fact_benchmark': [
        ('Benchmark Figures', 'COUNTROWS(fact_benchmark)', '0'),
        ('Reproduced %', 'DIVIDE(CALCULATE(COUNTROWS(fact_benchmark), LEFT(fact_benchmark[Result], 5) = "Match"), '
                         'COUNTROWS(fact_benchmark))', '0.0%'),
        ('AI Errors Found', 'CALCULATE(COUNTROWS(fact_benchmark), fact_benchmark[Who was right] = "App (AI was wrong)") + 0', '0'),
    ],
    'fact_circuit_tie': [
        ('Unexplained Circuit Cost', 'SUM(fact_circuit_tie[Unexplained cost])', '#,##0.00'),
    ],
    'fact_circuit': [
        ('Circuits', 'COUNTROWS(fact_circuit)', '0'),
    ],
}


def write_table(tdir: str, table: str, cols: list[tuple[str, str]]):
    lines = [f'table {q(table)}', f'\tlineageTag: {tag(table)}', '']
    for m, expr, fmt in MEASURES.get(table, []):
        lines += [f'\tmeasure {q(m)} = {expr}', f'\t\tformatString: {fmt}', f'\t\tlineageTag: {tag(table, "m", m)}', '']
    for c, t in cols:
        lines += [f'\tcolumn {q(c)}', f'\t\tdataType: {t}']
        if t != 'string':
            lines.append('\t\tformatString: ' + ('0' if t == 'int64' else '#,##0.00'))
        lines += [f'\t\tlineageTag: {tag(table, c)}', '\t\tsummarizeBy: ' + ('sum' if t != 'string' else 'none'),
                  f'\t\tsourceColumn: {c}', '', '\t\tannotation SummarizationSetBy = Automatic', '']
    mtypes = ', '.join('{"%s", %s}' % (c.replace('"', '""'), {'string': 'type text', 'int64': 'Int64.Type', 'double': 'type number'}[t])
                       for c, t in cols)
    m = [
        'let',
        f'    Source = Csv.Document(File.Contents(DatasetFolder & "{table}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        '    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),',
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{mtypes}}}, "en-GB")',
        'in',
        '    Typed',
    ]
    lines += [f'\tpartition {q(table)} = m', '\t\tmode: import', '\t\tsource =']
    lines += ['\t\t\t\t' + x for x in m]
    lines += ['', '\tannotation PBI_ResultType = Table', '']
    with open(os.path.join(tdir, f'{table}.tmdl'), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('\n'.join(lines))


# --------------------------------------------------------------------------- report (PBIR-legacy report.json)
def _src(entity):
    return {'Name': 't', 'Entity': entity, 'Type': 0}


def visual(vid, vtype, x, y, w, h, title, entity, roles: dict, sort=None):
    """roles: {'Category': [('col','Name')], 'Values': [('measure','Name')]}"""
    select, proj = [], {}
    for role, fields in roles.items():
        proj[role] = []
        for kind, name in fields:
            ref = f'{entity}.{name}'
            key = 'Measure' if kind == 'measure' else 'Column'
            select.append({key: {'Expression': {'SourceRef': {'Source': 't'}}, 'Property': name}, 'Name': ref})
            proj[role].append({'queryRef': ref})
    sv = {'visualType': vtype, 'projections': proj,
          'prototypeQuery': {'Version': 2, 'From': [_src(entity)], 'Select': select},
          'drillFilterOtherVisuals': True,
          'vcObjects': {'title': [{'properties': {
              'show': {'expr': {'Literal': {'Value': 'true'}}},
              'text': {'expr': {'Literal': {'Value': "'" + title.replace("'", "''") + "'"}}}}}]}}
    if sort:
        kind, name, direction = sort
        key = 'Measure' if kind == 'measure' else 'Column'
        sv['prototypeQuery']['OrderBy'] = [{'Direction': direction, 'Expression': {
            key: {'Expression': {'SourceRef': {'Source': 't'}}, 'Property': name}}}]
    cfg = {'name': vid, 'layouts': [{'id': 0, 'position': {'x': x, 'y': y, 'z': 0, 'width': w, 'height': h}}],
           'singleVisual': sv}
    return {'x': x, 'y': y, 'z': 0, 'width': w, 'height': h, 'config': json.dumps(cfg), 'filters': '[]'}


def textbox(vid, x, y, w, h, text):
    cfg = {'name': vid, 'layouts': [{'id': 0, 'position': {'x': x, 'y': y, 'z': 0, 'width': w, 'height': h}}],
           'singleVisual': {'visualType': 'textbox', 'drillFilterOtherVisuals': True,
                            'objects': {'general': [{'properties': {'paragraphs': [{'textRuns': [
                                {'value': text, 'textStyle': {'fontSize': '11pt'}}]}]}}]}}}
    return {'x': x, 'y': y, 'z': 0, 'width': w, 'height': h, 'config': json.dumps(cfg), 'filters': '[]'}


def pages():
    S = ('col', 'SAC')
    sl = lambda p, x=0, y=0, w=200, h=300: visual(f'{p}slicer', 'slicer', x, y, w, h, 'SAC', 'dim_sac', {'Values': [S]})
    card = lambda p, i, x, ent, m, t: visual(f'{p}card{i}', 'card', x, 0, 200, 110, t, ent, {'Values': [('measure', m)]})
    P = []
    # 1 Portfolio
    v = [sl('pf'), card('pf', 1, 210, 'dim_sac', 'SACs', 'SACs investigated'),
         card('pf', 2, 420, 'dim_sac', 'YTD Margin', 'FY26 YTD margin (£)'),
         card('pf', 3, 630, 'dim_sac', 'Total GBP At Stake', '£ at stake'),
         card('pf', 4, 840, 'dim_sac', 'Total High Findings', 'High findings'),
         card('pf', 5, 1050, 'fact_checks', 'Checks Passed %', 'Control checks passed'),
         visual('pftable', 'tableEx', 210, 120, 1060, 330, 'SAC portfolio', 'dim_sac',
                {'Values': [S, ('col', 'Customer'), ('col', 'FY26 YTD Revenue'), ('col', 'FY26 YTD Margin'),
                            ('col', 'FY25 Margin'), ('col', 'GBP at stake'), ('col', 'High findings'),
                            ('col', 'In Both (count)'), ('col', 'In SAC only (count)'), ('col', 'In OneBill only (count)'),
                            ('col', 'Chase items')]}),
         visual('pfbar', 'clusteredBarChart', 0, 460, 640, 250, 'Findings by type', 'fact_findings',
                {'Category': [('col', 'Flag')], 'Y': [('measure', 'Findings')]}, ('measure', 'Findings', 2)),
         visual('pfsev', 'donutChart', 650, 460, 620, 250, 'Findings by severity', 'fact_findings',
                {'Category': [('col', 'Severity')], 'Y': [('measure', 'Findings')]})]
    P.append(('Portfolio', v))
    # 2 Reconciliation
    v = [sl('rc'), card('rc', 1, 210, 'dim_sac', 'Accounts In Both', 'In both'),
         card('rc', 2, 420, 'dim_sac', 'Accounts SAC Only', 'In SAC report only'),
         card('rc', 3, 630, 'dim_sac', 'Accounts OneBill Only', 'On OneBill only'),
         card('rc', 4, 840, 'fact_recon_account', 'Match Rate %', 'Account match rate'),
         card('rc', 5, 1050, 'dim_sac', 'Accounts To Chase', 'Accounts to chase'),
         visual('rcreason', 'clusteredBarChart', 0, 310, 420, 400, 'Why accounts do not match', 'fact_recon_account',
                {'Category': [('col', 'Reason')], 'Y': [('measure', 'Accounts')]}, ('measure', 'Accounts', 2)),
         visual('rctable', 'tableEx', 430, 120, 840, 380, 'Account reconciliation', 'fact_recon_account',
                {'Values': [S, ('col', 'Status'), ('col', 'Reason'), ('col', 'Billing Account'), ('col', 'Sub Sector'),
                            ('col', 'OneBill (per SAC)'), ('col', 'OneBill (actual)'), ('col', 'SAC Amount'),
                            ('col', 'OneBill Amount'), ('col', 'Difference')]}),
         visual('rcissues', 'tableEx', 430, 510, 840, 200, 'Bill file issues', 'fact_bill_issues',
                {'Values': [S, ('col', 'OneBill'), ('col', 'Issue'), ('col', 'Detail'), ('col', 'Impact')]})]
    P.append(('Reconciliation', v))
    # 3 P&L deep dive
    v = [sl('pl', h=200), visual('plfy', 'slicer', 0, 210, 200, 120, 'Financial year', 'fact_pnl', {'Values': [('col', 'FY')]}),
         visual('pltype', 'slicer', 0, 340, 200, 140, 'Internal / External', 'fact_pnl', {'Values': [('col', 'Type')]}),
         visual('plline', 'lineChart', 210, 0, 1060, 300, 'Monthly margin: FY25 vs FY26 (£)', 'fact_pnl',
                {'Category': [('col', 'Period')], 'Series': [('col', 'FY')], 'Y': [('measure', 'Total Margin')]},
                ('col', 'Period', 1)),
         visual('plprod', 'clusteredBarChart', 210, 310, 500, 400, 'Margin by product', 'fact_pnl',
                {'Category': [('col', 'Product')], 'Y': [('measure', 'Total Margin')]}, ('measure', 'Total Margin', 1)),
         visual('plmatrix', 'tableEx', 720, 310, 550, 400, 'Product summary (FY26 YTD vs FY25)', 'fact_product',
                {'Values': [S, ('col', 'Product'), ('col', 'Revenue'), ('col', 'Cost'), ('col', 'Margin'),
                            ('col', 'FY25 Revenue'), ('col', 'FY25 Margin'), ('col', 'Internal Revenue')]})]
    P.append(('P&L Deep Dive', v))
    # 4 Circuit & voice
    v = [sl('ci'), card('ci', 1, 210, 'fact_circuit', 'Circuits', 'Mapped circuits'),
         card('ci', 2, 420, 'dim_sac', 'Live Circuit Rental', 'Live circuit rental (£/month)'),
         card('ci', 3, 630, 'fact_circuit_tie', 'Unexplained Circuit Cost', 'UKP cost with no circuit (£/month)'),
         visual('citie', 'tableEx', 210, 120, 1060, 200, 'Circuit rental vs UKP cost (latest period)', 'fact_circuit_tie',
                {'Values': [S, ('col', 'Product'), ('col', 'Live circuits'), ('col', 'Circuit rental'), ('col', 'UKP cost'),
                            ('col', 'Unexplained cost'), ('col', 'Tie-out')]}),
         visual('cistatus', 'donutChart', 0, 330, 400, 380, 'Live vs presumed ceased', 'fact_circuit',
                {'Category': [('col', 'Status')], 'Y': [('measure', 'Circuits')]}),
         visual('cilist', 'tableEx', 410, 330, 860, 380, 'Circuit evidence', 'fact_circuit',
                {'Values': [S, ('col', 'OR Circuit ID'), ('col', 'Product'), ('col', 'Status'), ('col', 'Rate'),
                            ('col', 'Description'), ('col', 'Town'), ('col', 'Postcode')]})]
    P.append(('Circuit & Voice Evidence', v))
    # 5 Findings & tracker
    v = [sl('fd', h=250), visual('fdsev', 'slicer', 0, 260, 200, 200, 'Severity', 'fact_findings', {'Values': [('col', 'Severity')]}),
         visual('fdtable', 'tableEx', 210, 0, 1060, 710, 'Findings (tracker view) — with action and source', 'fact_findings',
                {'Values': [S, ('col', 'Severity'), ('col', 'Product'), ('col', 'Flag'), ('col', 'Impact GBP'),
                            ('col', 'Finding'), ('col', 'Action'), ('col', 'Circuit IDs'), ('col', 'Source')]})]
    P.append(('Findings & Tracker', v))
    # 6 Accuracy & controls
    v = [card('ac', 1, 0, 'fact_benchmark', 'Reproduced %', 'Figures reproduced'),
         card('ac', 2, 210, 'fact_benchmark', 'AI Errors Found', 'AI figures wrong'),
         card('ac', 3, 420, 'fact_checks', 'Checks Passed %', 'Checks passed'),
         card('ac', 4, 630, 'fact_checks', 'Checks Failed', 'Checks failed'),
         visual('accmp', 'tableEx', 0, 120, 1270, 300, 'AI chat vs rule-based app', 'ref_ai_vs_rules',
                {'Values': [('col', 'Order'), ('col', 'Dimension'), ('col', 'AI chat'), ('col', 'Rule-based app')]},
                ('col', 'Order', 1)),
         visual('acwho', 'donutChart', 0, 430, 330, 280, 'Benchmark: who was right', 'fact_benchmark',
                {'Category': [('col', 'Who was right')], 'Y': [('measure', 'Benchmark Figures')]}),
         visual('acbench', 'tableEx', 340, 430, 470, 280, 'Benchmark detail (102 chat figures)', 'fact_benchmark',
                {'Values': [('col', 'SAC'), ('col', 'Metric'), ('col', 'AI chat value'), ('col', 'App value'),
                            ('col', 'Result'), ('col', 'Explanation')]}),
         visual('acchecks', 'tableEx', 820, 430, 450, 280, 'Control checks (this run)', 'fact_checks',
                {'Values': [('col', 'SAC'), ('col', 'Check'), ('col', 'Result'), ('col', 'Value')]})]
    P.append(('Accuracy & Controls', v))
    return P


def report_sections() -> list[dict]:
    return [{'name': f'Section{i + 1:02d}', 'displayName': title, 'width': 1280, 'height': 720, 'visualContainers': vis}
            for i, (title, vis) in enumerate(pages())]


def main():
    tables = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(DS, '*.csv')))
    if 'dim_sac' not in tables:
        raise SystemExit('dataset/dim_sac.csv not found — run "python run.py --all" (and benchmark.py) first.')
    sm = os.path.join(HERE, f'{NAME}.SemanticModel')
    rp = os.path.join(HERE, f'{NAME}.Report')
    for d in (sm, rp):
        shutil.rmtree(d, ignore_errors=True)
    tdir = os.path.join(sm, 'definition', 'tables')
    os.makedirs(tdir)
    os.makedirs(rp)
    w = lambda path, text: open(path, 'w', encoding='utf-8', newline='\r\n').write(text)
    w(os.path.join(HERE, f'{NAME}.pbip'), json.dumps({
        '$schema': 'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json',
        'version': '1.0', 'artifacts': [{'report': {'path': f'{NAME}.Report'}}],
        'settings': {'enableAutoRecovery': True}}, indent=2))
    w(os.path.join(sm, 'definition.pbism'), json.dumps({'version': '4.0', 'settings': {}}, indent=2))
    w(os.path.join(sm, 'definition', 'database.tmdl'), 'database\n\tcompatibilityLevel: 1550\n')
    model = ['model Model', '\tculture: en-GB', '\tdefaultPowerBIDataSourceVersion: powerBI_V3',
             '\tsourceQueryCulture: en-GB', '\tdataAccessOptions', '\t\tlegacyRedirects', '\t\treturnErrorValuesAsNull', '',
             'annotation PBI_QueryOrder = ' + json.dumps(['DatasetFolder'] + tables), '']
    model += [f'ref table {q(t)}' for t in tables]
    w(os.path.join(sm, 'definition', 'model.tmdl'), '\n'.join(model) + '\n')
    w(os.path.join(sm, 'definition', 'expressions.tmdl'),
      'expression DatasetFolder = "C:\\UKP\\dataset\\" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
      f'\tlineageTag: {tag("param")}\n\n\tannotation PBI_ResultType = Text\n')
    rels = []
    allcols = {t: col_types(os.path.join(DS, f'{t}.csv')) for t in tables}
    colnames = {c.lower() for cols in allcols.values() for c, _ in cols}
    mnames = [m for ms in MEASURES.values() for m, _, _ in ms]
    clash = [m for m in mnames if m.lower() in colnames] + [m for m in mnames if mnames.count(m) > 1]
    if clash:
        raise SystemExit(f'Measure names clash with column names (Power BI is case-insensitive): {clash}')
    for t in tables:
        cols = allcols[t]
        write_table(tdir, t, cols)
        if t != 'dim_sac' and any(c == 'SAC' for c, _ in cols) and not t.startswith('ref_'):
            rels += [f'relationship {tag("rel", t)}', f'\tfromColumn: {q(t)}.SAC', '\ttoColumn: dim_sac.SAC', '']
    w(os.path.join(sm, 'definition', 'relationships.tmdl'), '\n'.join(rels))
    # report: enhanced PBIR folder format (the format verified in the Power BI service)
    sections = report_sections()
    for path, text in report_parts(sections, model_folder=f'../{NAME}.SemanticModel').items():
        full = os.path.join(rp, *path.split('/'))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        w(full, text)
    w(os.path.join(HERE, '.gitignore'), '**/.pbi/localSettings.json\n**/.pbi/cache.abf\n')
    print(f'Wrote {os.path.relpath(HERE, ROOT)}/{NAME}.pbip with {len(tables)} tables and {len(sections)} report pages.')


if __name__ == '__main__':
    main()

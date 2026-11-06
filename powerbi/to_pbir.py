"""Turn the page plan (build_pbip.pages()) into the enhanced PBIR report format that the Power BI
service renders (verified by publishing it): definition/pages/<page>/page.json + visuals/<id>/visual.json,
plus the base report settings and theme saved from a report Power BI itself created (powerbi/pbir_base/).
"""
from __future__ import annotations

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, 'pbir_base')
SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition'
_LIT = lambda v: {'expr': {'Literal': {'Value': v}}}


def _field(sel):
    kind = 'Measure' if 'Measure' in sel else 'Column'
    return kind, sel[kind]['Property']


def _blank_filter(name, ent, prop):
    col = {'Column': {'Expression': {'SourceRef': {'Source': 's'}}, 'Property': prop}}
    return {'filters': [{'name': name, 'field': {'Column': {'Expression': {'SourceRef': {'Entity': ent}}, 'Property': prop}},
                         'type': 'Advanced',
                         'filter': {'Version': 2, 'From': [{'Name': 's', 'Entity': ent, 'Type': 0}],
                                    'Where': [{'Condition': {'Not': {'Expression': {'Comparison': {
                                        'ComparisonKind': 0, 'Left': col, 'Right': {'Literal': {'Value': 'null'}}}}}}}]}}]}


def page_parts(sections: list[dict]) -> dict[str, str]:
    """sections: [{'name','displayName','width','height','visualContainers':[legacy containers]}]"""
    parts, order = {}, []
    for sec in sections:
        pid = sec['name']
        order.append(pid)
        parts[f'definition/pages/{pid}/page.json'] = {
            '$schema': f'{SCHEMA}/page/2.1.0/schema.json', 'name': pid, 'displayName': sec['displayName'],
            'displayOption': 'FitToPage', 'height': sec['height'], 'width': sec['width']}
        for z, vc in enumerate(sec['visualContainers']):
            cfg = json.loads(vc['config'])
            sv, vid = cfg['singleVisual'], cfg['name']
            visual = {'visualType': sv['visualType'], 'drillFilterOtherVisuals': True}
            fc = None
            if 'prototypeQuery' in sv:
                ent = sv['prototypeQuery']['From'][0]['Entity']
                by_ref = {s['Name']: s for s in sv['prototypeQuery']['Select']}
                qs = {}
                for role, projs in sv['projections'].items():
                    qs[role] = {'projections': []}
                    for p in projs:
                        kind, prop = _field(by_ref[p['queryRef']])
                        qs[role]['projections'].append({
                            'field': {kind: {'Expression': {'SourceRef': {'Entity': ent}}, 'Property': prop}},
                            'queryRef': p['queryRef'], 'nativeQueryRef': prop})
                q = {'queryState': qs}
                if 'OrderBy' in sv['prototypeQuery']:
                    ob = sv['prototypeQuery']['OrderBy'][0]
                    kind = 'Measure' if 'Measure' in ob['Expression'] else 'Column'
                    q['sortDefinition'] = {'sort': [{'field': {kind: {'Expression': {'SourceRef': {'Entity': ent}},
                                                                     'Property': ob['Expression'][kind]['Property']}},
                                                     'direction': 'Ascending' if ob['Direction'] == 1 else 'Descending'}],
                                           'isDefaultSort': False}
                visual['query'] = q
                if sv['visualType'] == 'slicer':          # hide the (Blank) entry
                    first = qs['Values']['projections'][0]['field']
                    k = list(first)[0]
                    fc = _blank_filter(vid + 'nb', ent, first[k]['Property'])
            if 'vcObjects' in sv:
                visual['visualContainerObjects'] = sv['vcObjects']
            if 'objects' in sv:
                visual['objects'] = sv['objects']
            if sv['visualType'] == 'card':                # value only; the title already names the measure
                visual['objects'] = {'categoryLabels': [{'properties': {'show': _LIT('false')}}],
                                     'labels': [{'properties': {'fontSize': _LIT('20D')}}]}
            vj = {'$schema': f'{SCHEMA}/visualContainer/2.0.0/schema.json', 'name': vid,
                  'position': {'x': vc['x'], 'y': vc['y'], 'z': z * 1000, 'height': vc['height'],
                               'width': vc['width'], 'tabOrder': z * 1000},
                  'visual': visual}
            if fc:
                vj['filterConfig'] = fc
            parts[f'definition/pages/{pid}/visuals/{vid}/visual.json'] = vj
    parts['definition/pages/pages.json'] = {'$schema': f'{SCHEMA}/pagesMetadata/1.1.0/schema.json',
                                            'pageOrder': order, 'activePageName': order[0]}
    return {k: json.dumps(v, indent=2) for k, v in parts.items()}


def base_parts() -> dict[str, str]:
    out = {}
    for p in glob.glob(os.path.join(BASE, '**', '*.json'), recursive=True):
        out[os.path.relpath(p, BASE).replace(os.sep, '/')] = open(p, encoding='utf-8').read()
    return out


def pbir_by_path(model_folder: str) -> str:
    return json.dumps({'version': '4.0', 'datasetReference': {'byPath': {'path': model_folder}}}, indent=2)


def pbir_by_connection(dataset_id: str) -> str:
    """Binding to a semantic model in the Power BI service (format the Fabric API accepts)."""
    return json.dumps({'version': '1.0', 'datasetReference': {'byPath': None, 'byConnection': {
        'connectionString': None, 'pbiServiceModelId': None, 'pbiModelVirtualServerName': 'sobe_wowvirtualserver',
        'pbiModelDatabaseName': dataset_id, 'name': 'EntityDataSource', 'connectionType': 'pbiServiceXmlaStyleLive'}}})


def report_parts(sections, *, model_folder: str | None = None, dataset_id: str | None = None) -> dict[str, str]:
    parts = base_parts()
    parts.update(page_parts(sections))
    parts['definition.pbir'] = pbir_by_path(model_folder) if model_folder else pbir_by_connection(dataset_id)
    return parts

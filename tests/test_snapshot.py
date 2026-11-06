import base64,json,re
import pandas as pd
from powerbi.snapshot import build

def test_snapshot_embeds_rows_and_has_no_external_data_path(tmp_path):
    data=tmp_path/'data';data.mkdir()
    pd.DataFrame([{'SAC':'00123','Customer':'Example','FY26 YTD Revenue':123.45}]).to_csv(data/'dim_sac.csv',index=False)
    out=tmp_path/'project';build(str(data),str(out))
    text=(out/'UKP.SemanticModel/definition/tables/dim_sac.tmdl').read_text()
    payload=re.search(r'Text.Combine\(\{([^}]+)\}',text).group(1)
    rows=json.loads(base64.b64decode(''.join(json.loads('['+payload+']'))))
    assert rows==[['00123','Example',123.45]]
    assert 'Table.FromRows(Rows, {' in text
    assert 'File.Contents' not in text and 'DatasetFolder' not in text
    assert (out/'UKP.pbip').exists()
    for p in out.rglob('*.json'):json.loads(p.read_text())

def test_empty_financial_results_keep_project_valid(tmp_path):
    data=tmp_path/'data';data.mkdir()
    pd.DataFrame([{'SAC':'TEST','Customer':'Example'}]).to_csv(data/'dim_sac.csv',index=False)
    pd.DataFrame(columns=['SAC','FY','Period','Revenue','Cost','Margin']).to_csv(data/'fact_pnl.csv',index=False)
    out=tmp_path/'project';build(str(data),str(out))
    text=(out/'UKP.SemanticModel/definition/tables/fact_pnl.tmdl').read_text()
    assert 'dataType: double' in text
    assert 'Snapshot margin' not in text

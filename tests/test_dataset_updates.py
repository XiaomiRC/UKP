from types import SimpleNamespace
import pandas as pd
from ukp.export import write_dataset


def recon(services=None):
    return SimpleNamespace(customer='Example',summary={'SAC':'TEST','Bill total used':0},accounts=pd.DataFrame(columns=['SAC','Billing Account']),services=services if services is not None else pd.DataFrame(),bills=pd.DataFrame(columns=['SAC','OneBill']),issues=[],checks=[{'SAC':'TEST','Area':'Reconciliation','Result':'PASS'}])


def test_partial_update_preserves_headline_checks_and_clears_services(tmp_path):
    pd.DataFrame([{'SAC':'TEST','Customer':'Example','FY26 YTD Revenue':123,'GBP at stake':20}]).to_csv(tmp_path/'dim_sac.csv',index=False)
    pd.DataFrame([{'SAC':'TEST','Area':'Deep dive','Result':'WARN'}]).to_csv(tmp_path/'fact_checks.csv',index=False)
    pd.DataFrame([{'SAC':'TEST','Service Number':'OLD'}]).to_csv(tmp_path/'fact_recon_service.csv',index=False)
    write_dataset(str(tmp_path),'TEST',recon=recon())
    head=pd.read_csv(tmp_path/'dim_sac.csv')
    assert head['FY26 YTD Revenue'].iloc[0]==123
    assert set(pd.read_csv(tmp_path/'fact_checks.csv')['Area'])=={'Deep dive','Reconciliation'}
    assert pd.read_csv(tmp_path/'fact_recon_service.csv').empty
    assert head.columns.is_unique


def test_repeat_reconciliation_does_not_duplicate_fields(tmp_path):
    write_dataset(str(tmp_path),'TEST',recon=recon())
    write_dataset(str(tmp_path),'TEST',recon=recon())
    assert len(pd.read_csv(tmp_path/'dim_sac.csv'))==1
    assert len(pd.read_csv(tmp_path/'fact_checks.csv'))==1

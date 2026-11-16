import pandas as pd
import pytest
from ukp.loaders import load_bill,BILL_TOTAL

def test_missing_rental_dates_are_optional(tmp_path):
 p=tmp_path/'VP00000001.csv'
 pd.DataFrame([{'Service number':'S1','Source account':'A1','Account':'VP00000001','Service type':'Voice',BILL_TOTAL:'-10'}]).to_csv(p,index=False,encoding='latin1')
 bill=load_bill(str(p))
 assert bill.df[BILL_TOTAL].iloc[0]==-10
 assert bill.df.rent_start.isna().all()

def test_invalid_charge_is_rejected(tmp_path):
 p=tmp_path/'VP00000001.csv'
 pd.DataFrame([{'Service number':'S1','Source account':'A1','Account':'VP00000001','Service type':'Voice',BILL_TOTAL:'invalid'}]).to_csv(p,index=False,encoding='latin1')
 with pytest.raises(ValueError,match='CSV rows: 2'):load_bill(str(p))

def test_role_resolution_preserves_original_path(tmp_path):
 from ukp.loaders import PeriodFiles
 p=tmp_path/'P07-2026 circuit - customer - sac MAPPING.XLSB';p.touch()
 assert PeriodFiles.discover(str(tmp_path)).files['mapping']==str(p)
 custom=tmp_path/'custom.xlsb';custom.touch()
 assert PeriodFiles.discover(str(tmp_path),{'mapping':custom.name}).files['mapping']==str(custom)

def test_multiple_roles_rejected(tmp_path):
 from ukp.loaders import PeriodFiles
 p=tmp_path/'custom.xlsb';p.touch()
 with pytest.raises(ValueError,match='multiple roles'):
  PeriodFiles.discover(str(tmp_path),{'mapping':p.name,'voice':p.name})

def test_cli_private_rules_no_nameerror(tmp_path):
 import run,json
 p=tmp_path/'rules.json';p.write_text(json.dumps({'known_bulk_bills':['VP00000001']}))
 with pytest.raises(SystemExit):run.main(['--private-rules',str(p),'--sac','TEST01','--sac-reports',str(tmp_path),'--recon-only'])

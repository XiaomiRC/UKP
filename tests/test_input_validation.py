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

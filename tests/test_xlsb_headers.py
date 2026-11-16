from types import SimpleNamespace
from unittest.mock import patch
import pytest
from ukp.loaders import read_xlsb,PeriodFiles

class Context:
 def __init__(self,rows):self.values=rows
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def get_sheet(self,name):return self
 def rows(self,**kwargs):return iter([[SimpleNamespace(v=v) for v in row] for row in self.values])

def test_leading_blank_rows_preserve_header_and_data(tmp_path,monkeypatch):
 monkeypatch.setenv('UKP_MEMORY_ONLY','1')
 p=tmp_path/'example.xlsb';p.touch()
 with patch('pyxlsb.open_workbook',return_value=Context([[None,None],[' ',''],['SAC','Revenue'],['TEST01',12.5]])):
  d=read_xlsb(str(p),'Data')
 assert list(d.columns)==['SAC','Revenue']
 assert d.iloc[0].to_dict()=={'SAC':'TEST01','Revenue':12.5}

def test_empty_sheet_has_actionable_error(tmp_path,monkeypatch):
 monkeypatch.setenv('UKP_MEMORY_ONLY','1');p=tmp_path/'empty.xlsb';p.touch()
 with patch('pyxlsb.open_workbook',return_value=Context([[None]])),pytest.raises(ValueError,match='sheet is empty'):
  read_xlsb(str(p),'Data')

def test_missing_wd4_column_names_workbook_and_sheet():
 import pandas as pd
 with patch('ukp.loaders.read_xlsb',return_value=pd.DataFrame({'Wrong':[1]})),pytest.raises(ValueError,match='example.xlsb / Data: missing required columns:'):
  PeriodFiles('',files={'wd4':'example.xlsb'}).wd4()

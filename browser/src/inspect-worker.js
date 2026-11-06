self.onmessage=async({data})=>{try{
 const {loadPyodide}=await import(/* @vite-ignore */new URL('runtime/pyodide.mjs',data.base).href);
 const py=await loadPyodide({indexURL:new URL('runtime/',data.base).href});await py.loadPackage(['pandas']);
 const engine=await fetch(new URL('engine.zip',data.base),{cache:'no-cache'});py.unpackArchive(new Uint8Array(await engine.arrayBuffer()),'zip',{extractDir:'/app'});
 py.FS.writeFile('/input',new Uint8Array(data.bytes));py.globals.set('input_name',data.name);py.globals.set('requested_sheet',data.sheet||'');
 const preview=await py.runPythonAsync(`
import sys,json
sys.path.insert(0,'/app')
import pandas as pd
if input_name.lower().endswith('.csv'):
 try: df=pd.read_csv('/input',nrows=50,encoding='utf-8-sig')
 except UnicodeDecodeError: df=pd.read_csv('/input',nrows=50,encoding='latin1')
 sheets=[];chosen=None
elif input_name.lower().endswith('.xlsb'):
 from pyxlsb import open_workbook
 with open_workbook('/input') as wb:
  sheets=wb.sheets;chosen=requested_sheet or sheets[0]
  with wb.get_sheet(chosen) as sh:
   import itertools
   rows=[[c.v for c in row] for row in itertools.islice(sh.rows(),51)]
 df=pd.DataFrame(rows[1:],columns=rows[0])
else:
 xl=pd.ExcelFile('/input',engine='openpyxl');sheets=xl.sheet_names;chosen=requested_sheet or sheets[0]
 df=pd.read_excel(xl,sheet_name=chosen,nrows=50)
required={'Service number','Source account','Account','Service type','Total charges before VAT  (£)'}
validation=('OneBill CSV columns present' if required.issubset(set(df.columns)) else 'Preview only: required OneBill columns are missing') if not sheets else ('Enterprise sheet present; further SAC validation occurs during investigation' if 'Enterprise' in sheets else 'Workbook preview; eligibility depends on required UKP role and sheets')
json.dumps({'validation':validation,'file':input_name,'sheets':sheets,'preview_sheet':chosen,'preview':'First 50 rows only; not a completed investigation','columns':list(map(str,df.columns)),'rows':df.fillna('').astype(str).values.tolist()},indent=2)
`);postMessage({preview});
}catch(e){postMessage({error:'Cannot inspect file: '+e.message});}};

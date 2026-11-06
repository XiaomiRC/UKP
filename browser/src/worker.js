import {zipSync} from 'fflate';
self.onmessage=async({data})=>{
 try{
  const base=data.base;
  postMessage({status:'Loading Python runtime and bundled analysis libraries…'});
  const {loadPyodide}=await import(/* @vite-ignore */new URL('runtime/pyodide.mjs',base).href);
  const py=await loadPyodide({indexURL:new URL('runtime/',base).href,stdout:s=>postMessage({log:s}),stderr:s=>postMessage({log:s})});
  await py.loadPackage(['pandas','pyyaml']);
  const engine=await fetch(new URL('engine.zip',base));if(!engine.ok)throw Error('Analysis engine is unavailable. Rebuild application assets.');
  py.unpackArchive(new Uint8Array(await engine.arrayBuffer()),'zip',{extractDir:'/app'});
  for(const dir of ['sac','bills','period','outputs','dataset'])py.FS.mkdirTree('/work/'+dir);
  for(const file of data.files){const name=file.name;if(name.includes('/')||name.includes('\\'))throw Error('Invalid input filename');py.FS.writeFile('/work/'+file.category+'/'+name,new Uint8Array(file.bytes));}
  py.globals.set('browser_mode',data.mode);py.globals.set('browser_sacs',data.sacs.join(' '));py.globals.set('browser_date',data.date);py.globals.set('browser_audit',JSON.stringify(data.audit||[]));
  postMessage({status:'Running investigation locally. Large period workbooks can take several minutes.'});
  const summary=await py.runPythonAsync(`
import os, sys, json, warnings
warnings.filterwarnings('ignore', category=FutureWarning)
os.environ['UKP_MEMORY_ONLY']='1'
os.environ['UKP_CACHE']='/work/cache'
os.environ['UKP_REPORTING_DATE']=browser_date
sys.path.insert(0, '/app')
import run
used=set()
from js import postMessage as send, Object
from pyodide.ffi import to_js
def status(path,state): send(to_js({'fileStatus':{'file':os.path.basename(str(path)),'status':state}},dict_converter=Object.fromEntries))
def track(function):
 def wrapped(path,*args,**kwargs):
  status(path,'Processing')
  try:
   result=function(path,*args,**kwargs)
   used.add(str(path));status(path,'Used')
   return result
  except Exception:
   status(path,'Failed to read or validate');raise
 return wrapped
run.load_bill=track(run.load_bill)
run.load_sac_report=track(run.load_sac_report)
import ukp.loaders as loaders
loaders.read_xlsb=track(loaders.read_xlsb)
args=['--sac',*browser_sacs.split(),'--sac-reports','/work/sac','--bills','/work/bills','--period','/work/period','--out','/work/outputs','--dataset','/work/dataset']
if browser_mode!='both': args.append('--'+browser_mode+'-only')
results=run.main(args)
checks=[];findings=[];accounts=[]
for result in results:
 r,d=result['recon'],result['dd']
 if r is not None:
  checks.extend(r.checks)
  accounts.extend(r.accounts.fillna('').to_dict('records'))
 if d is not None:
  checks.extend(d.checks)
  findings.extend(d.findings.fillna('').to_dict('records'))
for result in results:
 if result['dd'] is not None:
  d=result['dd']
  from ukp.export import _upsert
  _upsert('/work/dataset/fact_voice.csv',d.voice,d.sac)
usage=[]
for category in ['sac','bills','period']:
 for name in os.listdir('/work/'+category):
  path='/work/'+category+'/'+name
  usage.append({'file':name,'status':'Used' if path in used else 'Skipped','reason':'Read by investigation' if path in used else 'Not referenced by selected investigation'})
import csv
audit=json.loads(browser_audit)
manifest=[]
for entry in audit:
 record=next((u for u in usage if u['file']==entry.get('name')),None)
 manifest.append({'file':entry['file'],'status':record['status'] if entry.get('included') and record else entry.get('status','Skipped'),'reason':record['reason'] if entry.get('included') and record else entry.get('reason','Not required')})
with open('/work/dataset/file_status.csv','w') as f:
 writer=csv.DictWriter(f,fieldnames=['file','status','reason']);writer.writeheader();writer.writerows(manifest or usage)
send(to_js({'status':'Preparing interactive dashboard…'},dict_converter=Object.fromEntries))
dashboard={}
schemas={}
import pandas as pd
for name in os.listdir('/work/dataset'):
 if name.endswith('.csv'):
  frame=pd.read_csv('/work/dataset/'+name,dtype=str,keep_default_na=False)
  dashboard[name[:-4]]=frame.to_dict('records')
  schemas[name[:-4]]=list(frame.columns)
export_error=''
try:
 send(to_js({'status':'Building self-contained Power BI project…'},dict_converter=Object.fromEntries))
 from powerbi.snapshot import build
 build('/work/dataset','/work/powerbi')
except Exception as ex: export_error=str(ex)
json.dumps({'dashboard_schema':schemas,'dashboard':dashboard,'export_error':export_error,'checks':checks,'findings':findings,'accounts':accounts,'usage':usage}, default=str)
`);
  const files=[];const archive={};
  function collect(path,prefix){for(const name of py.FS.readdir(path)){if(name==='.'||name==='..')continue;const full=path+'/'+name;if(py.FS.isDir(py.FS.stat(full).mode))collect(full,prefix+name+'/');else{const bytes=py.FS.readFile(full);archive[prefix+name]=bytes; if(name.endsWith('.xlsx'))files.push({name:prefix+name,bytes});}}}
  if(!JSON.parse(summary).export_error&&py.FS.analyzePath('/work/powerbi').exists)collect('/work/powerbi','powerbi/');
  collect('/work/outputs','reports/');collect('/work/dataset','dataset/');
  const result=JSON.parse(summary);
  const audit=(data.audit||[]).map(f=>{const used=result.usage.find(u=>u.file===f.name);return {file:f.file,status:f.included?(used?.status||'Not completed'):f.status,reason:f.included?(used?.reason||'Investigation did not finish'):f.reason};});
  if(audit.length){const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';archive['dataset/file_status.csv']=new TextEncoder().encode(['file,status,reason',...audit.map(f=>[f.file,f.status,f.reason].map(quote).join(','))].join('\n'));}
  const project=Object.fromEntries(Object.entries(archive).filter(([name])=>name.startsWith('powerbi/')));
  if(Object.keys(project).length)files.push({name:'UKP-PowerBI.zip',bytes:zipSync(project)});
  files.unshift({name:'UKP-results.zip',bytes:zipSync(archive)});
  postMessage({files,summary:result},files.map(f=>f.bytes.buffer));
 }catch(e){postMessage({error:e.message||String(e)});}
};

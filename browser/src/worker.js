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
  py.globals.set('browser_mode',data.mode);py.globals.set('browser_sacs',data.sacs.join(' '));py.globals.set('browser_date',data.date);
  postMessage({status:'Running investigation locally. Large period workbooks can take several minutes.'});
  const summary=await py.runPythonAsync(`
import os, sys, json, warnings
warnings.filterwarnings('ignore', category=FutureWarning)
os.environ['UKP_MEMORY_ONLY']='1'
os.environ['UKP_CACHE']='/work/cache'
os.environ['UKP_REPORTING_DATE']=browser_date
sys.path.insert(0, '/app')
import run
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
json.dumps({'checks':checks,'findings':findings,'accounts':accounts}, default=str)
`);
  const files=[];const archive={};
  function collect(path,prefix){for(const name of py.FS.readdir(path)){if(name==='.'||name==='..')continue;const full=path+'/'+name;if(py.FS.isDir(py.FS.stat(full).mode))collect(full,prefix+name+'/');else{const bytes=py.FS.readFile(full);archive[prefix+name]=bytes; if(name.endsWith('.xlsx'))files.push({name:prefix+name,bytes});}}}
  collect('/work/outputs','reports/');collect('/work/dataset','dataset/');
  files.unshift({name:'UKP-results.zip',bytes:zipSync(archive)});
  postMessage({files,summary:JSON.parse(summary)},files.map(f=>f.bytes.buffer));
 }catch(e){postMessage({error:e.message||String(e)});}
};

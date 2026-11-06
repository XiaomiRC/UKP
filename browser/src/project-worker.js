import {zipSync} from 'fflate';
self.onmessage=async({data})=>{try{const {loadPyodide}=await import(/* @vite-ignore */new URL('runtime/pyodide.mjs',data.base).href);const py=await loadPyodide({indexURL:new URL('runtime/',data.base).href});await py.loadPackage(['pandas']);const response=await fetch(new URL('engine.zip',data.base));if(!response.ok)throw Error('Engine unavailable');py.unpackArchive(new Uint8Array(await response.arrayBuffer()),'zip',{extractDir:'/app'});py.globals.set('snapshot',JSON.stringify(data.summary));await py.runPythonAsync(`
import sys,os,json,pandas as pd
sys.path.insert(0,'/app');os.makedirs('/dataset',exist_ok=True)
s=json.loads(snapshot)
for table,rows in s['dashboard'].items():
 pd.DataFrame(rows,columns=s['dashboard_schema'][table]).to_csv('/dataset/'+table+'.csv',index=False)
from powerbi.snapshot import build
build('/dataset','/project')
`);const archive={};function visit(folder,prefix){for(const name of py.FS.readdir(folder)){if(name==='.'||name==='..')continue;const path=folder+'/'+name;if(py.FS.isDir(py.FS.stat(path).mode))visit(path,prefix+name+'/');else archive[prefix+name]=py.FS.readFile(path);}}visit('/project','powerbi/');const bytes=zipSync(archive);postMessage({bytes},[bytes.buffer]);}catch(e){postMessage({error:e.message});}};

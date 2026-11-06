import {loadPyodide} from 'pyodide';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..');
const py=await loadPyodide({indexURL:path.join(root,'browser/public/runtime/')});
await py.loadPackage(['pandas','pyyaml']);
py.unpackArchive(new Uint8Array(fs.readFileSync(path.join(root,'browser/public/engine.zip'))),'zip',{extractDir:'/app'});
py.FS.mkdirTree('/work');
py.FS.mount(py.FS.filesystems.NODEFS,{root:path.join(root,'inputs')},'/work');
py.globals.set('recon_only',process.argv.includes('--recon'));
const result=await py.runPythonAsync(`
import sys,os,json
sys.path.insert(0,'/app')
os.environ['UKP_MEMORY_ONLY']='1'
os.environ['UKP_CACHE']='/tmp/cache'
os.environ['UKP_REPORTING_DATE']='2026-11-06'
import run
args=['--all','--sac-reports','/work/sac_reports','--bills','/work/bills','--period','/work/P06','--out','/out','--dataset','/dataset']
if recon_only: args.append('--recon-only')
results=run.main(args)
json.dumps([{'sac':r['sac'],'summary':r['recon'].summary,'headline':r['dd'].headline if r['dd'] else None} for r in results],default=str)
`);
fs.writeFileSync('/tmp/ukp-wasm-results.json',result);
console.log('WASM_RESULTS_SAVED');

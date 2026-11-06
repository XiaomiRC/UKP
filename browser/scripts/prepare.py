"""Bundle only application source, runtime and explicitly named dependencies."""
import hashlib, json, shutil, subprocess, zipfile
from pathlib import Path
import openpyxl, et_xmlfile, pyxlsb
ROOT=Path(__file__).resolve().parents[2]
PUBLIC=ROOT/'browser/public'
RUNTIME=PUBLIC/'runtime'; RUNTIME.mkdir(parents=True,exist_ok=True)
PACKAGE=ROOT/'browser/node_modules/pyodide'
version=json.loads((PACKAGE/'package.json').read_text())['version']
for name in ['pyodide.mjs','pyodide.asm.js','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json']:
 shutil.copyfile(PACKAGE/name,RUNTIME/name)
(RUNTIME/'package.json').write_text('{"type":"commonjs"}')
lock=json.loads((PACKAGE/'pyodide-lock.json').read_text()); seen=set()
def fetch(name):
 if name in seen:return
 seen.add(name); p=lock['packages'][name]
 for dependency in p['depends']:fetch(dependency)
 dest=RUNTIME/p['file_name']
 if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest()!=p['sha256']:
  subprocess.run(['curl','-fSL','--retry','2',f'https://cdn.jsdelivr.net/pyodide/v{version}/full/{p["file_name"]}','-o',str(dest)],check=True)
 if hashlib.sha256(dest.read_bytes()).hexdigest()!=p['sha256']:raise RuntimeError(f'Hash mismatch: {name}')
for name in ['pandas','pyyaml']:fetch(name)
with zipfile.ZipFile(PUBLIC/'engine.zip','w',zipfile.ZIP_DEFLATED) as archive:
 for folder in ['ukp','config']:
  for path in (ROOT/folder).rglob('*'):
   if path.is_file() and path.suffix in ['.py','.yaml']:archive.write(path,path.relative_to(ROOT))
 for name in ['powerbi/__init__.py','powerbi/snapshot.py','powerbi/build_pbip.py','powerbi/to_pbir.py']:
  archive.write(ROOT/name,name)
 for path in (ROOT/'powerbi/pbir_base').rglob('*.json'):
  archive.write(path,path.relative_to(ROOT))
 archive.write(ROOT/'run.py','run.py')
 for module in [openpyxl,et_xmlfile,pyxlsb]:
  folder=Path(module.__file__).parent
  for path in folder.rglob('*.py'):archive.write(path,Path(folder.name)/path.relative_to(folder))
print(f'Prepared Pyodide {version}; {len(seen)} packages; application sources only.')

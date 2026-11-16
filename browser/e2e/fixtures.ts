import {execFileSync} from 'node:child_process';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'ukp-synthetic-'));
const root=path.resolve(import.meta.dirname,'../..');
const python=fs.existsSync(path.join(root,'.venv/bin/python'))?path.join(root,'.venv/bin/python'):'python3';
execFileSync(python,['-c',`
import openpyxl,sys,os,csv
folder=sys.argv[1]
w=openpyxl.Workbook();s=w.active;s.title='Enterprise'
s.append(['Billing Account Number','OneBill Account Number','Telephone Number','Service ID','Billing System','Sub Sector','Legal Entity Name','Product Name','SAC Code','SAC Name','Discounted Price','Contract End Date'])
s.append(['A001','VP00000001','S001','S001','Example','Example','Example Ltd','Voice','TEST01','Example Ltd','10','2030-01-01'])
s=w.create_sheet('Onebills');s.append(['VP00000001','Active','Dedicated'])
w.save(os.path.join(folder,'TEST01_EXAMPLE.xlsx'))
with open(os.path.join(folder,'VP00000001.csv'),'w',encoding='latin1',newline='') as f:
 c=csv.writer(f);c.writerow(['Service number','Source account','Account','Service type','Total charges before VAT  (£)','Rental start date','Rental end date','Rental days']);c.writerow(['S001','A001','VP00000001','Voice','10','','',''])
`,folder]);
export const report=path.join(folder,'TEST01_EXAMPLE.xlsx');
fs.copyFileSync(path.join(folder,'VP00000001.csv'),path.join(folder,'VP00000002.csv'));
export const bills=[path.join(folder,'VP00000001.csv'),path.join(folder,'VP00000002.csv')];
process.on('exit',()=>fs.rmSync(folder,{recursive:true,force:true}));

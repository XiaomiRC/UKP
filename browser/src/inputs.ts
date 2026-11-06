import {Unzip, UnzipInflate} from 'fflate';
export type InputFile = {path:string;file:File;kind:'sac'|'bill'|'period';period:string};
const LIMIT=1024**3, SINGLE=500*1024**2, COUNT=500;
export function classify(file:File,path:string):InputFile|null {
 const name=path.split('/').pop()||'';
 if(name.startsWith('~$')) return null;
 if(/\.csv$/i.test(name)&&/^VP\d{8}/i.test(name)) return {path,file,kind:'bill',period:''};
 if(/\.xlsx$/i.test(name)&&/^[A-Z0-9]+-?_/.test(name.toUpperCase())&&!/tracker|reconciliation|deep_dive/i.test(name))return {path,file,kind:'sac',period:''};
 if(/\.xlsb$/i.test(name)) {const m=name.match(/P(\d{2})[-_](20\d{2})/i)||path.match(/\bP(\d{2})\b.*?(20\d{2})/i);return {path,file,kind:'period',period:m?`${m[2]}-P${m[1]}`:''};}
 return null;
}
async function inspectZip(file:File){
 const tail=new Uint8Array(await file.slice(Math.max(0,file.size-65557)).arrayBuffer());const view=new DataView(tail.buffer);let end=-1;
 for(let i=tail.length-22;i>=0;i--)if(view.getUint32(i,true)===0x06054b50&&i+22+view.getUint16(i+20,true)===tail.length){end=i;break;}
 if(end<0)throw Error('Invalid or incomplete ZIP archive.');
 const count=view.getUint16(end+10,true),size=view.getUint32(end+12,true),offset=view.getUint32(end+16,true);
 if(view.getUint16(end+4,true)||view.getUint16(end+6,true)||count>COUNT||size>16*1024**2||offset+size>file.size)throw Error('Split, ZIP64, or oversized archive is unsupported.');
 const bytes=await file.slice(offset,offset+size).arrayBuffer(),central=new DataView(bytes);let cursor=0,total=0;
 for(let n=0;n<count;n++){
  if(cursor+46>bytes.byteLength||central.getUint32(cursor,true)!==0x02014b50)throw Error('Invalid ZIP directory.');
  if(central.getUint16(cursor+8,true)&1)throw Error('Password-protected ZIP archives are unsupported.');
  if(![0,8].includes(central.getUint16(cursor+10,true)))throw Error('ZIP compression method is unsupported.');
  const expanded=central.getUint32(cursor+24,true);total+=expanded;
  if(expanded>SINGLE||total>LIMIT)throw Error('ZIP expanded size exceeds the safety limit.');
  cursor+=46+central.getUint16(cursor+28,true)+central.getUint16(cursor+30,true)+central.getUint16(cursor+32,true);
 }
 if(cursor!==bytes.byteLength)throw Error('Invalid ZIP directory length.');
}
export async function importFiles(files:File[],existing:InputFile[],signal?:AbortSignal){
 const excluded:{path:string;reason:string;size:number;file?:File}[]=[];
 const result=[...existing];let expanded=existing.reduce((n,f)=>n+f.file.size,0),count=existing.length,ignored=0;
 function accept(path:string,bytes:Uint8Array|File){
  if(++count>COUNT)throw Error('Maximum 500 files per session.');
  expanded+=bytes instanceof File?bytes.size:bytes.byteLength;
  if(expanded>LIMIT)throw Error('Maximum expanded selection size is 1 GB.');
  const f=bytes instanceof File?bytes:new File([bytes as BlobPart],path.split('/').pop());
  if(f.size>SINGLE)throw Error('Maximum individual file size is 500 MB.');
  const item=classify(f,path);if(!item){ignored++;excluded.push({path,size:f.size,reason:nameReason(path),file:/\.(csv|xlsx|xlsb)$/i.test(path)?f:undefined});return;}
  if(result.some(r=>r.path===path)){excluded.push({path,size:f.size,file:f,reason:'Duplicate path; original retained'});return;}
  result.push(item);
 }
 for(const f of files){
  signal?.throwIfAborted();
  if(f.size>SINGLE)throw Error('Maximum individual file size is 500 MB.');
  if(!/\.zip$/i.test(f.name)){accept(f.webkitRelativePath||f.name,f);continue;}
  await inspectZip(f);
  let failure:Error|null=null,entries=0,actual=0,unfinished=0;
  const unzip=new Unzip(entry=>{
   if(++entries>COUNT){failure=Error('ZIP contains more than 500 entries.');return;}
   const name=entry.name.replace(/\\/g,'/');
   if(name.startsWith('/')||/^[A-Za-z]:/.test(name)||name.split('/').includes('..')||name.includes('\0')||/\.zip$/i.test(name)){failure=Error('ZIP contains an unsafe path or nested archive.');return;}
   if(name.endsWith('/'))return;
   unfinished++;
   const chunks:Uint8Array[]=[];let size=0;
   entry.ondata=(error,data,final)=>{
    if(failure)return;
    if(error){failure=Error('Unsupported, corrupt, or encrypted ZIP.');return;}
    size+=data.length;actual+=data.length;
    if(size>SINGLE||expanded+actual>LIMIT){failure=Error('ZIP expanded size exceeds the safety limit.');entry.terminate();return;}
    chunks.push(data);
    if(final){unfinished--;const all=new Uint8Array(size);let pos=0;for(const c of chunks){all.set(c,pos);pos+=c.length;}actual-=size;try{accept(name,all);}catch(e){failure=e as Error;}}
   };
   try{entry.start();}catch(e){failure=e as Error;}
  });
  unzip.register(UnzipInflate);
  for(let offset=0;offset<f.size;offset+=65536){signal?.throwIfAborted();if(failure)throw failure;unzip.push(new Uint8Array(await f.slice(offset,offset+65536).arrayBuffer()),offset+65536>=f.size);}
  if(failure)throw failure;if(!entries||unfinished)throw Error('ZIP contains no readable entries or is truncated.');
 }
 return {files:result,ignored,excluded};
}

function nameReason(path:string){if(path.split('/').pop()?.startsWith('~$'))return 'Temporary Excel file';if(/\.(csv|xlsx|xlsb)$/i.test(path))return 'Filename does not identify a supported UKP input; available for inspection';return 'Unsupported file type';}

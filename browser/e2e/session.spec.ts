import {test,expect} from '@playwright/test';
test('clear discards pending private rules read',async({page})=>{
 await page.addInitScript(()=>{const original=File.prototype.text;File.prototype.text=function(){if(this.name==='private.json')return new Promise<string>(resolve=>{(window as any).finishRead=()=>resolve('{"known_bulk_bills":["VP00000001"]}');});return original.call(this);};});
 await page.goto('./');await page.getByLabel('Private rules file (optional JSON)',{exact:true}).setInputFiles({name:'private.json',mimeType:'application/json',buffer:Buffer.from('{}')});
 await page.getByRole('button',{name:'Clear session / Cancel'}).click();await page.evaluate(()=>(window as any).finishRead());await expect(page.getByRole('status')).toContainText('Session cleared');
});
test('clear prevents a pending inspection read from posting to its worker',async({page})=>{
 await page.addInitScript(()=>{const original=File.prototype.arrayBuffer;File.prototype.arrayBuffer=function(){if(this.name==='pending.csv')return new Promise<ArrayBuffer>(resolve=>{(window as any).finishBuffer=()=>resolve(new ArrayBuffer(0));});return original.call(this);};const post=Worker.prototype.postMessage;(window as any).workerPosts=0;Worker.prototype.postMessage=function(...args:any[]){(window as any).workerPosts++;return (post as any).apply(this,args);};});
 await page.goto('./');await page.locator('input[type=file]').first().setInputFiles({name:'pending.csv',mimeType:'text/csv',buffer:Buffer.from('a,b\n1,2')});await page.getByRole('button',{name:'Inspect file',exact:true}).click();await page.getByRole('button',{name:'Clear session / Cancel'}).click();await page.evaluate(()=>(window as any).finishBuffer());await expect(page.getByRole('status')).toContainText('Session cleared');expect(await page.evaluate(()=>(window as any).workerPosts)).toBe(0);
});

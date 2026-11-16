import {test,expect} from '@playwright/test';
test('clear discards pending private rules read',async({page})=>{
 await page.addInitScript(()=>{const original=File.prototype.text;File.prototype.text=function(){if(this.name==='private.json')return new Promise<string>(resolve=>{(window as any).finishRead=()=>resolve('{"known_bulk_bills":["VP00000001"]}');});return original.call(this);};});
 await page.goto('./');await page.getByLabel('Private rules file (optional JSON)',{exact:true}).setInputFiles({name:'private.json',mimeType:'application/json',buffer:Buffer.from('{}')});
 await page.getByRole('button',{name:'Clear session / Cancel'}).click();await page.evaluate(()=>(window as any).finishRead());await expect(page.getByRole('status')).toContainText('Session cleared');
});

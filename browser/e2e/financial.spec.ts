import {test,expect} from '@playwright/test';
import {report} from './fixtures';
test('comparison respects customer coverage and reset restores defaults',async({page})=>{
 await page.addInitScript(()=>{(window as any).Worker=class{onmessage:any;onerror:any;terminate(){}postMessage(){const data={dim_sac:[{SAC:'TEST01'},{SAC:'TEST02'}],fact_pnl:[{SAC:'TEST01',FY:'FY26',Period:'P01',Margin:'5'},{SAC:'TEST02',FY:'FY26',Period:'P02',Margin:'5'},{SAC:'TEST01',FY:'FY25',Period:'P01',Margin:'10'},{SAC:'TEST01',FY:'FY25',Period:'P02',Margin:'20'}]};queueMicrotask(()=>this.onmessage({data:{files:[],summary:{dashboard:data,checks:[],findings:[],accounts:[],usage:[]}}}));}};});
 await page.goto('./');await page.locator('input[type=file]').first().setInputFiles(report);await page.getByRole('combobox',{name:'Activity',exact:true}).selectOption('recon');await page.getByRole('button',{name:'Select all',exact:true}).click();await page.getByRole('button',{name:'Run 1 selected SAC',exact:true}).click();
 await page.getByRole('combobox',{name:'Dashboard view',exact:true}).selectOption('fact_pnl');await page.getByRole('combobox',{name:'Dashboard SAC',exact:true}).selectOption('TEST01');await page.getByRole('combobox',{name:'Financial year',exact:true}).selectOption('FY25');
 await expect(page.getByRole('button',{name:'P01: 10',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'P02: 20',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Reset filters',exact:true}).click();await expect(page.getByRole('combobox',{name:'Financial year',exact:true})).toHaveValue('FY26');await expect(page.getByRole('combobox',{name:'Dashboard SAC',exact:true})).toHaveValue('');
});

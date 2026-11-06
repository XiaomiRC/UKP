import {test,expect} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';import {zipSync} from 'fflate';
const root=path.resolve(import.meta.dirname,'../..');
test('real reconciliation produces local downloads without upload requests',async({page})=>{
 const network:any[]=[];page.on('request',r=>network.push({url:r.url(),method:r.method()}));
 await page.goto('./');
 const reports=fs.readdirSync(path.join(root,'inputs/sac_reports')).filter(n=>n.startsWith('TEST01_')).map(n=>path.join(root,'inputs/sac_reports',n));
 const bills=fs.readdirSync(path.join(root,'inputs/bills')).filter(n=>n.endsWith('.csv')).map(n=>path.join(root,'inputs/bills',n));
 await page.locator('input[type=file]').nth(0).setInputFiles([...reports,...bills]);
 await page.getByLabel('Activity').selectOption('recon');await page.getByRole('button',{name:'Select all',exact:true}).click();
 await page.getByRole('button',{name:/Run 1 selected SAC/}).click();
 await expect(page.getByRole('link',{name:'Download all reports + CSV dataset'})).toBeVisible({timeout:150000});
 const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download all reports + CSV dataset'}).click();
 expect((await download).suggestedFilename()).toBe('UKP-results.zip');
 expect(network.filter(r=>r.method!=='GET')).toEqual([]);
 expect(network.filter(r=>!r.url.startsWith(new URL(page.url()).origin+'/'))).toEqual([]);
 expect(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length}))).toEqual({local:0,session:0});
 await page.screenshot({path:process.env.UKP_TEST_BASE_URL?'/tmp/ukp-browser-live-success.png':'/tmp/ukp-browser-local-success.png',fullPage:true});
 await page.getByRole('button',{name:'Clear session / Cancel'}).click();await expect(page.getByRole('status')).toContainText('Session cleared');await expect(page.getByRole('link')).toHaveCount(0);
});
test('ZIP inputs appear in inventory and can be removed',async({page})=>{
 await page.goto('./');await page.locator('input[type=file]').nth(2).setInputFiles({name:'inputs.zip',mimeType:'application/zip',buffer:Buffer.from(zipSync({'sac_reports/X1234_EXAMPLE.xlsx':new Uint8Array([1]),'bills/VP12345678.csv':new Uint8Array([1])}))});
 await expect(page.getByRole('status')).toContainText('2 supported files');await page.getByText('2 supported files · review inventory').click();await expect(page.getByRole('cell',{name:'sac_reports/X1234_EXAMPLE.xlsx',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Remove sac_reports/X1234_EXAMPLE.xlsx',exact:true}).click();await expect(page.getByText('1 supported files · review inventory')).toBeVisible();
});

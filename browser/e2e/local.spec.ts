import {test,expect} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';import {zipSync,unzipSync} from 'fflate';
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
 await expect(page.getByRole('heading',{name:'Interactive dashboard'})).toBeVisible();await page.getByLabel('Dashboard view',{exact:true}).selectOption('fact_recon_account');await expect(page.getByRole('button',{name:/^In Both:/})).toBeVisible();
 const powerDownload=page.waitForEvent('download');await page.getByRole('link',{name:'UKP-PowerBI.zip',exact:true}).click();const power=unzipSync(fs.readFileSync((await (await powerDownload).path())!));expect(Object.keys(power)).toContain('powerbi/UKP.pbip');const model=new TextDecoder().decode(power['powerbi/UKP.SemanticModel/definition/tables/dim_sac.tmdl']);expect(model).toContain('Binary.FromText');expect(model).not.toContain('File.Contents');
 const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download all reports + CSV dataset'}).click();
 const downloaded=await download;expect(downloaded.suggestedFilename()).toBe('UKP-results.zip');
 const contents=unzipSync(fs.readFileSync((await downloaded.path())!));const manifest=new TextDecoder().decode(contents['dataset/file_status.csv']);expect(manifest).toContain('Used');expect(manifest).toContain('Skipped');
 expect(network.filter(r=>r.method!=='GET')).toEqual([]);
 expect(network.filter(r=>!r.url.startsWith(new URL(page.url()).origin+'/'))).toEqual([]);
 expect(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length}))).toEqual({local:0,session:0});
 await page.screenshot({path:process.env.UKP_TEST_BASE_URL?'/tmp/ukp-browser-live-success.png':'/tmp/ukp-browser-local-success.png',fullPage:true});
 await page.getByRole('button',{name:'Clear session / Cancel'}).click();await expect(page.getByRole('status')).toContainText('Session cleared');await expect(page.getByRole('link')).toHaveCount(0);
});
test('ZIP inputs appear in inventory and can be removed',async({page})=>{
 await page.goto('./');await page.locator('input[type=file]').nth(2).setInputFiles({name:'inputs.zip',mimeType:'application/zip',buffer:Buffer.from(zipSync({'sac_reports/X1234_EXAMPLE.xlsx':new Uint8Array([1]),'bills/VP12345678.csv':new Uint8Array([1])}))});
 await expect(page.getByRole('status')).toContainText('2 files received');await page.getByText('2 supported files · review inventory').click();await expect(page.getByRole('cell',{name:'sac_reports/X1234_EXAMPLE.xlsx',exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:'Remove sac_reports/X1234_EXAMPLE.xlsx',exact:true}).click();await expect(page.getByText('1 supported files · review inventory')).toBeVisible();
});

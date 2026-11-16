import {test,expect} from '@playwright/test';
import {zipSync} from 'fflate';
test('missing mapping explains requirements and retains ZIP inputs',async({page})=>{
 await page.goto('./');
 await page.locator('input[type=file]').nth(2).setInputFiles({name:'period.zip',mimeType:'application/zip',buffer:Buffer.from(zipSync({'P07-2026 Products Data Extract.xlsb':new Uint8Array([1]),'P07-2026_MB Control File.xlsb':new Uint8Array([1]),'P06-2026-SAP Reco.xlsb':new Uint8Array([1])}))});
 await page.getByLabel('Period',{exact:true}).selectOption('2026-P07');
 const row=page.getByRole('row').filter({has:page.getByRole('cell',{name:'mapping',exact:true})});
 await expect(row).toContainText('Missing');await expect(row).toContainText('MB Control File is not a substitute');
 await expect(page.getByText(/Other period: P06/)).toBeVisible();
 await expect(page.getByRole('button',{name:'Use reconciliation only'})).toBeDisabled();
 await expect(page.getByText('3 supported files · review inventory')).toBeVisible();
});

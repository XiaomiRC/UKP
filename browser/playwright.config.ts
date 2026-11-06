import {defineConfig} from '@playwright/test';
const remote=process.env.UKP_TEST_BASE_URL;
export default defineConfig({testDir:'./e2e',timeout:180000,use:{baseURL:remote||'http://127.0.0.1:4173',headless:true,launchOptions:{executablePath:process.env.UKP_CHROMIUM||undefined}},webServer:remote?undefined:{command:'npm run preview -- --host 127.0.0.1 --port 4173',url:'http://127.0.0.1:4173',reuseExistingServer:true}});

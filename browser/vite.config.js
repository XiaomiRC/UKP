import {defineConfig} from 'vite';
export default defineConfig({base:'./',worker:{format:'es'},plugins:[{name:'development-csp',apply:'serve',transformIndexHtml(html){return html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/,'');}}]});

import {parentPort} from 'node:worker_threads';import fs from 'node:fs/promises';
globalThis.self=globalThis;
globalThis.postMessage=(data,transfer)=>parentPort.postMessage(data,transfer);
globalThis.fetch=async url=>{const u=new URL(url);if(u.protocol!=='file:')throw Error('Network requests are forbidden in this test');return new Response(await fs.readFile(u));};
const source=(await fs.readFile(new URL('../src/worker.js',import.meta.url),'utf8')).replace("from 'fflate'", `from '${import.meta.resolve('fflate')}'`).replace("indexURL:new URL('runtime/',base).href","indexURL:new URL('runtime/',base).pathname");
await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
parentPort.on('message',data=>self.onmessage({data}));

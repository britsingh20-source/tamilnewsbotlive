import {build} from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
await build({configFile:false,root:path.join(root,'standalone'),plugins:[react()],publicDir:path.join(root,'public'),build:{outDir:path.join(root,'.standalone-build/client'),emptyOutDir:true,minify:true}});
const assets={};
async function scan(dir){for(const item of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,item.name);if(item.isDirectory())await scan(p);else {const ext=path.extname(item.name);const mime={'.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.html':'text/html; charset=utf-8','.svg':'image/svg+xml'}[ext];if(!mime)throw Error('Unsupported asset type '+ext);assets['/'+path.relative(path.join(root,'.standalone-build/client'),p)]={mime,body:await fs.readFile(p,'utf8')};}}}
await scan(path.join(root,'.standalone-build/client'));
await fs.writeFile(path.join(root,'.standalone-build/assets.json'),JSON.stringify(assets));
await build({configFile:false,root,ssr:{noExternal:true},build:{ssr:path.join(root,'standalone/worker.ts'),outDir:path.join(root,'.standalone-build/worker'),emptyOutDir:true,minify:true,rollupOptions:{output:{entryFileNames:'index.js'}}}});
console.log('Standalone CRM built with '+Object.keys(assets).length+' embedded assets.');

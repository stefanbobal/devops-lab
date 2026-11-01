// Static server only. No uploads, model calls or access outside this app folder.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const port=Number(process.env.PORT||8008);
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.svg':'image/svg+xml'};
const allowed=new Set(['index.html','styles.css','app.mjs','data.mjs','judge_ui.mjs']);
const server=http.createServer(async(req,res)=>{try{
  const url=new URL(req.url,'http://localhost');const filename=decodeURIComponent(url.pathname)==='/'?'index.html':decodeURIComponent(url.pathname).slice(1);
  if(!['GET','HEAD'].includes(req.method)||!allowed.has(filename)){res.writeHead(404);res.end('Not found');return;}
  const data=await readFile(path.join(root,filename));
  res.writeHead(200,{'Content-Type':types[path.extname(filename)]||'text/plain','X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"});
  res.end(req.method==='HEAD'?undefined:data);
}catch{res.writeHead(400);res.end('Bad request');}});
server.listen(port,'127.0.0.1',()=>console.log(`LLM Homelab: http://127.0.0.1:${port} · local files stay in your browser`));

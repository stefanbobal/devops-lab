// Optional browser regression: npm install --no-save playwright; node test_judge_ui.cjs
// All API/provider responses are simulated. No paid model calls.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const http=require('node:http'),fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const allowed=new Set(['index.html','app.mjs','data.mjs','judge_ui.mjs','styles.css']);
 const server=http.createServer(async(req,res)=>{const name=req.url==='/'?'index.html':req.url.slice(1);if(!allowed.has(name)){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',name.endsWith('mjs')?'text/javascript':name.endsWith('css')?'text/css':'text/html');res.end(await fs.readFile(path.join(__dirname,name)));});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 let browser;
 try{
 browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
 const page=await browser.newPage({viewport:{width:1500,height:1100}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const rid='00000000-0000-0000-0000-000000000001',bid='00000000-0000-0000-0000-000000000002';
 const models=[{id:'ollama/gemma3:27b',provider:'ollama',model:'gemma3:27b',label:'gemma3:27b · lokálny',ready:true,reason:'Installed'},
   {id:'anthropic/claude-sonnet-5-5',provider:'anthropic',model:'claude-sonnet-5-5',label:'Claude Sonnet · cloud',ready:true,reason:'Configured, quota not verified'}];
 const worker={online:true,models},plans=[],starts=[],stops=[];let running=null,failPlan=false;
 await page.route('**/api/dataset',r=>r.fulfill({json:{reviewer:'sapops',files:[
   {path:'db/manifest.json',text:JSON.stringify({fingerprint:'judge-ui',created_at:'now',_database_id:rid,_database_name:'rag-dev-2026-10-31-v2',scenarios:[{id:'dev-hana-insufficient',incident:'Backup failed.',review_guidance:'Get logs.'}]})},
   {path:'db/calls/a.json',text:JSON.stringify({call_id:'a',scenario_id:'dev-hana-insufficient',status:'ok',llm_profile:'qwen38',embedding_profile:'bge',mode:'rag',answer:'Get the backup error.'})}]} }));
 await page.route('**/api/judge/options',r=>r.fulfill({json:{worker,runs:[{id:rid,name:'rag-dev-2026-10-31-v2',calls:480}],scenarios:['dev-hana-insufficient'],candidate_models:['qwen38'],modes:['rag'],rubrics_version:'v2',references_version:'empty',approved_references:0,prices:{models:{'anthropic:claude-sonnet-5-5':{input_per_million:2,output_per_million:10}}}}}));
 await page.route('**/api/judge/plan',async r=>{if(failPlan){await r.fulfill({status:400,json:{error:'Cena je neznáma.'}});return;}const body=r.request().postDataJSON();plans.push(body);await r.fulfill({json:{id:bid,status:'draft',plan:{selected:20,new_calls:body.max_calls,existing_skipped:0,planning_estimate_usd:.1,provider:'anthropic',model:'claude-sonnet-5-5',scenarios:{'dev-hana-insufficient':20},modes:{rag:20},estimate_note:'Planning only; not billing.'}}});});
 await page.route('**/api/judge/start',async r=>{const body=r.request().postDataJSON();starts.push(body);running={id:bid,status:'queued',plan:{model:'claude-sonnet-5-5',new_calls:3,selected:20},counts:{},created_at:'2026-11-01T18:00:00Z'};await r.fulfill({json:{id:bid,status:'queued'}});});
 await page.route('**/api/judge/stop',async r=>{stops.push(r.request().postDataJSON());running.stop_requested=true;await r.fulfill({json:{stop_requested:true}});});
 await page.route('**/api/judge/batches',r=>r.fulfill({json:{worker,batches:running?[running]:[]}}));
 await page.goto('http://127.0.0.1:'+server.address().port);
 await page.locator('#load-db').click();await page.locator('[data-view="judge"]').click();
 await page.waitForFunction(()=>document.querySelector('#judge-model').options.length===2);
 assert.equal(await page.locator('#judge-model').inputValue(),'ollama/gemma3:27b');
 assert.equal(await page.locator('#judge-budget').isDisabled(),true);
 await page.locator('#judge-model').selectOption('anthropic/claude-sonnet-5-5');
 assert.equal(await page.locator('#judge-context').isDisabled(),true);
 await page.locator('#judge-preview').click();await page.locator('#judge-start-row').waitFor();
 assert.equal(starts.length,0);assert.equal(await page.locator('#judge-start').isDisabled(),true);
 await page.locator('#judge-max-calls').fill('3');assert.equal(await page.locator('#judge-start-row').isHidden(),true);
 await page.locator('#judge-preview').click();await page.locator('#judge-start-row').waitFor();
 await page.locator('#judge-cloud-accept').check();await page.locator('#judge-start').click();
 await page.waitForFunction(()=>document.querySelector('[data-judge-stop]'));
 assert.equal(starts.length,1);assert.equal(starts[0].accept_cloud_cost,true);
 assert.equal(plans.at(-1).max_calls,3);assert.equal(plans.at(-1).pilot_size,20);
 assert.deepEqual(plans.at(-1).run_ids,[rid]);
 assert.ok(!JSON.stringify(plans).includes('api_key'));
 await page.locator('[data-judge-stop]').click();await page.waitForFunction(()=>document.querySelector('[data-judge-stop]').disabled);
 assert.equal(stops.length,1);
 await page.reload();await page.locator('#load-db').click();await page.locator('[data-view="judge"]').click();
 await page.waitForFunction(()=>document.querySelector('#judge-batches').textContent.includes('claude-sonnet'));
 assert.equal(starts.length,1); // Refresh must never restart the batch.
 failPlan=true;await page.locator('#judge-preview').click();await page.waitForFunction(()=>document.querySelector('#judge-control-error').textContent.includes('neznáma'));
 assert.equal(starts.length,1);
 if(process.env.JUDGE_SCREENSHOT)await page.screenshot({path:process.env.JUDGE_SCREENSHOT,fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
 await page.locator('#judge-results').click();await page.waitForFunction(()=>!document.querySelector('#review').hidden);
 assert.equal(await page.locator('#judged-only').isChecked(),true);
 assert.deepEqual(errors,[]);
 console.log('PASS: judge form, local/cloud selection, preview-only behavior, explicit cloud start, stale-plan invalidation, stop, reload persistence, errors, result navigation and mobile layout. Simulated API only.');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exit(1);});

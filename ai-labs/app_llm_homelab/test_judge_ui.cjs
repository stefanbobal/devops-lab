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
 const worker={online:true,models},plans=[],starts=[],stops=[];let running=null,failPlan=false,batchPolls=0;
 await page.route('**/api/dataset',r=>r.fulfill({json:{reviewer:'sapops',judge_evaluations:[{run_id:rid,call_id:'a',job_id:bid,status:'completed',config:{provider:'ollama',model:'gemma3:27b'},result:{summary:'Needs review',verdict:'needs_review',steps:[{quote:'Get the backup error.',technical:'unverified',reference_ids:[],reference_quote:'',reason:'Need current evidence',grounding:'current_evidence',priority:'now',citation:'none',risk:'diagnostic'}],validation_warnings:['test-warning-unverified <img src=x onerror=alert(1)>'],suggested_scores:{},critical_error:false},created_at:'2026-11-01T19:00:00Z'},
 {run_id:rid,call_id:'a',job_id:'old-bad',status:'invalid',created_at:'2026-11-01T18:00:00Z',error:'Old invalid',result:null},
 {run_id:rid,call_id:'a',job_id:'new-bad',status:'invalid',created_at:'2026-11-01T20:00:00Z',error:'New invalid',result:null},
 {run_id:rid,call_id:'b',job_id:'only-bad',status:'invalid',created_at:'2026-11-01T20:00:00Z',error:'Invalid critical_error',result:null}],files:[
   {path:'db/manifest.json',text:JSON.stringify({fingerprint:'judge-ui',created_at:'now',_database_id:rid,_database_name:'rag-dev-2026-10-31-v2',scenarios:[{id:'dev-hana-insufficient',incident:'Backup failed.',review_guidance:'Get logs.'}]})},
   {path:'db/calls/a.json',text:JSON.stringify({call_id:'a',scenario_id:'dev-hana-insufficient',status:'ok',llm_profile:'qwen38',embedding_profile:'bge',mode:'rag',answer:'Get the backup error.'})},
 {path:'db/calls/b.json',text:JSON.stringify({call_id:'b',scenario_id:'dev-hana-insufficient',status:'ok',llm_profile:'opus',embedding_profile:'bge',mode:'rag',answer:'Another model response.'})}]} }));
 await page.route('**/api/judge/options',r=>r.fulfill({json:{worker,runs:[{id:rid,name:'rag-dev-2026-10-31-v2',calls:480}],scenarios:['dev-hana-insufficient'],candidate_models:['qwen38'],modes:['rag'],rubrics_version:'v2',references_version:'empty',approved_references:0,prices:{models:{'anthropic:claude-sonnet-5-5':{input_per_million:2,output_per_million:10}}}}}));
 await page.route('**/api/judge/plan',async r=>{if(failPlan){await r.fulfill({status:400,json:{error:'Cena je neznáma.'}});return;}const body=r.request().postDataJSON();plans.push(body);await r.fulfill({json:{id:bid,status:'draft',plan:{selected:20,new_calls:body.max_calls,existing_skipped:0,planning_estimate_usd:.1,provider:'anthropic',model:'claude-sonnet-5-5',scenarios:{'dev-hana-insufficient':20},modes:{rag:20},estimate_note:'Planning only; not billing.'}}});});
 await page.route('**/api/judge/start',async r=>{const body=r.request().postDataJSON();starts.push(body);running={id:bid,status:'queued',plan:{model:'claude-sonnet-5-5',new_calls:3,selected:20},counts:{invalid:1},recent:[{job_id:bid,call_id:'a',scenario_id:'dev-hana-insufficient',status:'invalid',error:'Invalid critical_error',elapsed_s:11,usage:{input_tokens:100,output_tokens:50}}],created_at:'2026-11-01T18:00:00Z'};await r.fulfill({json:{id:bid,status:'queued'}});});
 await page.route('**/api/judge/stop',async r=>{stops.push(r.request().postDataJSON());running.stop_requested=true;await r.fulfill({json:{stop_requested:true}});});
 await page.route('**/api/judge/batches',r=>{batchPolls++;if(running)running.estimated_cost_usd=batchPolls/1000;return r.fulfill({json:{worker,batches:running?[running]:[]}});});
 await page.route('**/api/judge/output**',r=>r.fulfill({json:{job_id:bid,status:'invalid',error:'Invalid critical_error',raw_output:'{"critical_error":"false"} <img src=x onerror=alert(1)>'}}));
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
 const recent=page.locator('[data-judge-detail="recent/'+bid+'"]');
 await recent.locator(':scope > summary').click();
 const original=page.locator('[data-judge-detail="raw/'+bid+'/'+bid+'"]');
 await original.locator(':scope > summary').click();await original.locator('[data-judge-output]').click();
 await page.waitForFunction(()=>document.querySelector('.judge-raw').textContent.includes('critical_error'));
 const before=batchPolls;await new Promise(r=>setTimeout(r,4500));
 assert.ok(batchPolls>before);assert.equal(await recent.evaluate(d=>d.open),true);
 assert.equal(await original.evaluate(d=>d.open),true);
 assert.match(await page.locator('.judge-raw').innerText(),/"critical_error":"false"/);
 assert.equal(await page.locator('#judge-batches img').count(),0);
 await recent.locator(':scope > summary').click();
 await new Promise(r=>setTimeout(r,4500));assert.equal(await recent.evaluate(d=>d.open),false);
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
 assert.equal(await page.locator('#review-list button').count(),1);
 assert.equal(await page.locator('#judge-attempt').inputValue(),bid);
 assert.match(await page.locator('#judge-review-panel').innerText(),/starší platný posudok/);
 await page.locator('[data-score]').first().selectOption('1');
 await page.locator('#judge-attempt').selectOption('old-bad');
 assert.equal(await page.locator('#judge-fill').count(),0);
 assert.equal(await page.locator('[data-score]').first().inputValue(),'1');
 await page.locator('#judge-attempt').selectOption(bid);
 assert.equal(await page.locator('[data-score]').first().inputValue(),'1');
 await page.locator('#judge-fill').click();
 assert.match(await page.locator('#review-notes').inputValue(),new RegExp(bid));
 assert.match(await page.locator('.judge-panel').innerText(),/test-warning-unverified/);
 assert.equal(await page.locator('.judge-panel img').count(),0);
 await page.locator('#judged-only').uncheck();
 assert.equal(await page.locator('#review-list button').count(),2);
 await page.locator('#review-list button').nth(1).click();
 assert.match(await page.locator('#judge-review-panel').innerText(),/Pre túto konkrétnu odpoveď zatiaľ nie je platný/);
 assert.equal(await page.locator('.judge-panel').count(),0);
 assert.deepEqual(errors,[]);
 console.log('PASS: judge form, local/cloud selection, preview-only behavior, explicit cloud start, stale-plan invalidation, stop, reload persistence, errors, result navigation mobile layout, persistent expanded/collapsed details across changed polling responses and escaped original output. Simulated API only.');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exit(1);});

export const SCORE_FIELDS = ['relevance_0_2','evidence_0_2','citations_0_2','uncertainty_0_2','actionability_0_2'];
export function number(v) { if (v === null || v === undefined || String(v).trim()==='') return null; const n=Number(v); return Number.isFinite(n)?n:null; }
export function csvParse(text) {
  text=text.replace(/^\uFEFF/,''); const rows=[]; let row=[], cell='', quoted=false;
  for(let i=0;i<text.length;i++){const c=text[i]; if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else if(quoted||cell==='')quoted=!quoted;else throw Error('Neplatné CSV úvodzovky');}
    else if(c===','&&!quoted){row.push(cell);cell='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v!==''))rows.push(row);row=[];cell='';}else cell+=c;}
  if(quoted)throw Error('Neuzatvorené CSV pole'); if(cell!==''||row.length){row.push(cell);rows.push(row);} if(!rows.length)return [];
  const headers=rows.shift().map(h=>h.trim()); if(new Set(headers).size!==headers.length)throw Error('Duplicitné CSV stĺpce');
  return rows.map(r=>{if(r.length!==headers.length)throw Error('Nesprávny počet CSV stĺpcov');return Object.fromEntries(headers.map((h,i)=>[h,r[i]]));});
}
export function csvExport(rows, fields) {const escape=v=>`"${String(v??'').replaceAll('"','""')}"`;return '\uFEFF'+[fields.map(escape).join(','),...rows.map(r=>fields.map(f=>escape(r[f])).join(','))].join('\r\n');}
export const mean=values=>values.length?values.reduce((a,b)=>a+b,0)/values.length:null;
export function percentile(values,p){const a=values.filter(v=>number(v)!==null).map(Number).sort((a,b)=>a-b);return a.length?a[Math.max(0,Math.ceil(p*a.length)-1)]:null;}
export function pearson(points){if(points.length<3)return null;const x=mean(points.map(p=>p[0])),y=mean(points.map(p=>p[1]));let a=0,b=0,c=0;for(const [u,v]of points){a+=(u-x)*(v-y);b+=(u-x)**2;c+=(v-y)**2;}return b&&c?a/Math.sqrt(b*c):null;}
export function quality(review){const scores=SCORE_FIELDS.map(f=>number(review?.[f]));return scores.every(v=>v!==null&&Number.isInteger(v)&&v>=0&&v<=2)?scores.reduce((a,b)=>a+b,0):null;}
export function summarize(rows){const ok=rows.filter(r=>r.status==='ok');const cost=rows.map(r=>number(r.estimated_cost_usd));return {count:rows.length,ok:ok.length,fail:rows.length-ok.length,p50:percentile(ok.map(r=>r.llm_latency_s),.5),p95:percentile(ok.map(r=>r.llm_latency_s),.95),cost:cost.filter(v=>v!==null).reduce((a,b)=>a+b,0),unknown:cost.filter(v=>v===null).length,tokens:rows.reduce((a,r)=>a+(number(r.input_tokens)??0)+(number(r.output_tokens)??0),0),missingUsage:rows.filter(r=>number(r.input_tokens)===null||number(r.output_tokens)===null).length};}
export function groupModels(rows){const map=new Map();for(const r of rows){const k=r.llm_profile||r.model||'unknown';if(!map.has(k))map.set(k,[]);map.get(k).push(r);}return [...map].map(([name,rs])=>({name,...summarize(rs)}));}
const parent=p=>p.includes('/')?p.slice(0,p.lastIndexOf('/')):'samostatne-subory';
export function importDataset(files){
  const runs=new Map(), warnings=[];let skipped=0;
  function run(path){if(!runs.has(path))runs.set(path,{path,name:path.split('/').pop(),manifest:null,calls:new Map(),reviews:new Map(),contexts:[],csvOnly:true});return runs.get(path);}
  // Manifests first; calls and exports then merge by scoped call_id, JSON wins.
  for(const f of files.filter(f=>f.path.endsWith('/manifest.json')||f.path==='manifest.json')){try{const m=JSON.parse(f.text);if(!m||typeof m!=='object'||(m.scenarios!==undefined&&!Array.isArray(m.scenarios)))throw Error('Neplatná štruktúra manifestu');run(parent(f.path)).manifest=m;}catch(e){warnings.push(f.path+': '+e.message);}}
  const candidates=[];
  for(const f of files){const name=f.path.split('/').pop();try{
    if(name==='manifest.json')continue;
    if(f.path.includes('/contexts/')&&name.endsWith('.json')){run(f.path.split('/contexts/')[0]).contexts.push(JSON.parse(f.text));continue;}
    if(name.endsWith('.json')&&f.path.includes('/calls/')){const obj=JSON.parse(f.text);if(!obj.call_id)throw Error('Chýba call_id');candidates.push({run:run(f.path.split('/calls/')[0]),obj,priority:3});continue;}
    if(name.endsWith('.json')){const obj=JSON.parse(f.text);if(obj&&obj.call_id&&obj.scenario_id){candidates.push({run:run(parent(f.path)),obj,priority:3});continue;}}
    if(name.endsWith('.csv')){const rs=csvParse(f.text);if(!rs.length){skipped++;continue;}if(!('call_id'in rs[0])){skipped++;continue;}const target=run(parent(f.path));
      for(const obj of rs){if(!obj.call_id)continue;if(SCORE_FIELDS.some(k=>k in obj)&&!('answer'in obj)){target.reviews.set(obj.call_id,obj);continue;}
        if('answer'in obj||'status'in obj)candidates.push({run:target,obj,priority:name==='results.csv'?2:1});}
      continue;}
    skipped++;
  }catch(e){warnings.push(f.path+': '+e.message);}}
  candidates.sort((a,b)=>a.priority-b.priority);
  for(const {run:r,obj,priority}of candidates){const previous=r.calls.get(obj.call_id)||{};const clean=Object.fromEntries(Object.entries(obj).filter(([,v])=>v!==''&&v!==undefined));r.calls.set(obj.call_id,{...previous,...clean});if(priority===3)r.csvOnly=false;}
  const records=[],resultRuns=[];
  for(const r of runs.values()){if(!r.calls.size)continue;
    const manifest=r.manifest; r.id=manifest?.fingerprint&&manifest?.created_at?manifest.fingerprint+':'+manifest.created_at:r.path;
    if(!manifest)warnings.push(r.name+': chýba manifest; nastavenia a nezávislosť behov nevieme overiť.');
    if(r.csvOnly)warnings.push(r.name+': CSV import; úplné prompty, história alebo guidance môžu chýbať.');
    const scenarios=new Map((manifest?.scenarios||[]).map(s=>[s.id,s]));
    for(const obj of r.calls.values()){const scenario=scenarios.get(obj.scenario_id)||{};const record={...obj,run_id:r.id,run_name:r.name,key:JSON.stringify([r.id,obj.call_id]),mode:obj.mode|| (obj.embedding_profile==='none'?'no_history':'rag'),incident:scenario.incident||obj.incident||'',review_guidance:scenario.review_guidance||obj.review_guidance||'',review:r.reviews.get(obj.call_id)||{}};records.push(record);}
    resultRuns.push({...r,calls:undefined,reviews:undefined});
  }
  // Same imported run copied under another folder: one observation per run/call.
  const unique=new Map(records.map(r=>[r.key,r]));
  return {records:[...unique.values()],runs:[...new Map(resultRuns.map(r=>[r.id,r])).values()],warnings,skipped};
}
export function pairedComparisons(rows){
  const groups=new Map();for(const r of rows.filter(r=>r.status==='ok')){const key=JSON.stringify([r.scenario_id,r.llm_profile]);if(!groups.has(key))groups.set(key,{scenario:r.scenario_id,model:r.llm_profile,rag:[],no_history:[]});const g=groups.get(key);if(r.mode==='rag'||r.mode==='no_history')g[r.mode].push(r);}
  return [...groups.values()].filter(g=>g.rag.length&&g.no_history.length).map(g=>({...g,ragLatency:mean(g.rag.map(r=>number(r.llm_latency_s)).filter(v=>v!==null)),baseLatency:mean(g.no_history.map(r=>number(r.llm_latency_s)).filter(v=>v!==null))}));
}

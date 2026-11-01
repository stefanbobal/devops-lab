import test from 'node:test';
import assert from 'node:assert/strict';
import {csvParse,csvExport,importDataset,number,summarize,quality,pairedComparisons,pearson} from './data.mjs';
test('CSV handles multiline answers, escaped quotes, BOM, CRLF and roundtrip',()=>{
 const rows=[{call_id:'a',answer:'Text, "quote"\nand another line',estimated_cost_usd:''}];
 assert.deepEqual(csvParse(csvExport(rows,['call_id','answer','estimated_cost_usd'])),rows);
 assert.throws(()=>csvParse('a,b\n"unfinished,x'));
});
const call={call_id:'one',scenario_id:'s',llm_profile:'model',status:'ok',input_tokens:10,output_tokens:20,llm_latency_s:2,estimated_cost_usd:0};
const manifest={fingerprint:'fp',created_at:'time',scenarios:[{id:'s',incident:'Current incident',review_guidance:'Hidden rubric'}]};
test('JSON and exports deduplicate; JSON wins; rubric comes only from manifest',()=>{
 const data=importDataset([{path:'r/manifest.json',text:JSON.stringify(manifest)},{path:'r/calls/one.json',text:JSON.stringify({...call,answer:'JSON'})},{path:'r/results.csv',text:csvExport([{...call,answer:'CSV'}],Object.keys({...call,answer:''}))},{path:'r/quality_review.csv',text:'call_id,relevance_0_2\none,2'}]);
 assert.equal(data.records.length,1);assert.equal(data.records[0].answer,'JSON');assert.equal(data.records[0].review_guidance,'Hidden rubric');assert.equal(data.records[0].review.relevance_0_2,'2');
});
test('same call_id in different runs stays separate; copied run deduplicates',()=>{
 const files=['a','b'].flatMap((p,i)=>[{path:p+'/manifest.json',text:JSON.stringify({...manifest,created_at:'time'+i})},{path:p+'/calls/one.json',text:JSON.stringify(call)}]);
 assert.equal(importDataset(files).records.length,2);
 files.push({path:'copy/manifest.json',text:JSON.stringify({...manifest,created_at:'time0'})},{path:'copy/calls/one.json',text:JSON.stringify(call)});
 assert.equal(importDataset(files).records.length,2);
});
test('unknown cost and usage remain unknown rather than zero',()=>{
 const s=summarize([call,{...call,status:'error',input_tokens:null,output_tokens:null,estimated_cost_usd:''}]);
 assert.equal(s.unknown,1);assert.equal(s.missingUsage,1);assert.equal(s.ok,1);assert.equal(s.fail,1);assert.equal(s.cost,0);assert.equal(number(''),null);
});
test('scores require all five valid integer fields',()=>{
 assert.equal(quality({relevance_0_2:2}),null);
 assert.equal(quality(Object.fromEntries(['relevance_0_2','evidence_0_2','citations_0_2','uncertainty_0_2','actionability_0_2'].map(k=>[k,2]))),10);
});
test('paired baseline counted once, failed responses excluded',()=>{
 const rows=[{...call,mode:'rag'},{...call,mode:'rag',llm_latency_s:4},{...call,mode:'no_history',llm_latency_s:1},{...call,mode:'rag',status:'error',llm_latency_s:100}];
 const pairs=pairedComparisons(rows);assert.equal(pairs.length,1);assert.equal(pairs[0].no_history.length,1);assert.equal(pairs[0].ragLatency,3);
});
test('bad import is reported and cannot prevent valid records loading',()=>{
 const d=importDataset([{path:'r/calls/bad.json',text:'{'},{path:'r/calls/good.json',text:JSON.stringify(call)}]);
 assert.equal(d.records.length,1);assert.ok(d.warnings.length);assert.equal(pearson([[1,2],[2,4],[3,6]]),1);assert.equal(pearson([[1,2]]),null);
});

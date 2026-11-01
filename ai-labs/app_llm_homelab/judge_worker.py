"""Read-only plan by default. --execute reserves and evaluates selected DB answers via Ollama."""
import argparse
from collections import Counter
import json
import os
import time
import uuid
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from db_store import BASE, connect, read_json
from judge_core import SYSTEM, digest, packet, prompt, sample_rows, validate_result, deterministic_checks, approved_references, CONTRACT, calibration_report


def request_json(url, body=None, timeout=300):
    req = Request(url, data=None if body is None else json.dumps(body).encode(),
                  headers={'Content-Type':'application/json'})
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def ollama(body, config):
    result = request_json(config['host']+'/api/chat', {
        'model':config['model'], 'stream':False, 'format':'json', 'keep_alive':'5m',
        'messages':[{'role':'system','content':config['system']},{'role':'user','content':body}],
        'options':{'temperature':0,'seed':config['seed'],'num_ctx':config['num_ctx'],
                   'num_predict':config['max_output_tokens']}}, config['timeout'])
    usage = {key:result.get(key) for key in ('model','done','done_reason','prompt_eval_count',
             'eval_count','load_duration','prompt_eval_duration','eval_duration','total_duration')}
    return result.get('message',{}).get('content',''), usage


def selected_rows(conn, names, rubrics, limit, seed):
    rows=[]; found=set()
    for rid,name,cid,call,scenario in conn.execute('''SELECT c.run_id,r.name,c.call_id,c.data,s.data
        FROM llm_eval.calls c JOIN llm_eval.runs r ON r.id=c.run_id
        JOIN llm_eval.scenarios s ON s.run_id=c.run_id AND s.scenario_id=c.scenario_id
        WHERE r.name=ANY(%s) ORDER BY r.name,c.call_id''',(names,)):
        found.add(name)
        if call['status']=='ok':
            if call['scenario_id'] not in rubrics['scenarios']:
                raise ValueError('Missing rubric for '+call['scenario_id'])
            rows.append({'run_id':str(rid),'run_name':name,'call_id':cid,'call':call,'scenario':scenario})
    if found!=set(names): raise ValueError('Missing requested runs: '+','.join(sorted(set(names)-found)))
    if not rows: raise ValueError('No successful answers in selected runs')
    return sample_rows(rows,limit or len(rows),seed)


def should_skip(previous, retry_errors):
    # A running reservation can be an interrupted/uncertain external call. Never repeat automatically.
    return previous is not None and (previous[1] in ('completed','running') or not retry_errors)


def reserve(conn,row,data,config,retry_errors=False):
    from psycopg.types.json import Jsonb
    ih,ch=digest(data),digest(config)
    previous=conn.execute('''SELECT attempt,status FROM llm_eval.judge_jobs
        WHERE run_id=%s AND call_id=%s AND input_hash=%s AND config_hash=%s
        ORDER BY attempt DESC LIMIT 1''',(row['run_id'],row['call_id'],ih,ch)).fetchone()
    if should_skip(previous,retry_errors): return None
    job=str(uuid.uuid4())
    conn.execute('''INSERT INTO llm_eval.judge_jobs
        (id,run_id,call_id,input_hash,config_hash,attempt,status,input_data,config)
        VALUES (%s,%s,%s,%s,%s,%s,'running',%s,%s)''',
        (job,row['run_id'],row['call_id'],ih,ch,1 if previous is None else previous[0]+1,Jsonb(data),Jsonb(config)))
    return job


def finish(conn,job,status,raw,usage,elapsed,result=None,error=None):
    from psycopg.types.json import Jsonb
    conn.execute('''UPDATE llm_eval.judge_jobs SET status=%s,raw_output=%s,usage=%s,
        elapsed_s=%s,estimated_cost_usd=%s,error=%s,finished_at=now() WHERE id=%s AND status='running' ''',
        (status,raw,Jsonb(usage),elapsed,usage.get('estimated_cost_usd',0.0 if usage and 'usage_raw' not in usage else None),error,job))
    if result is not None:
        conn.execute('INSERT INTO llm_eval.judge_evaluations(job_id,data) VALUES (%s,%s)',(job,Jsonb(result)))


def make_system(row,config):
    rules=config.get('rubrics',{}).get('scenarios',{}).get(row['call']['scenario_id'],{})
    return config.get('system',SYSTEM)+'\nScore rubric:\n'+json.dumps(config.get('rubrics',{}).get('score_anchors',{}),ensure_ascii=False)+'\nScenario identifier: '+row['call']['scenario_id']+'\nScenario rubric:\n'+json.dumps(rules,ensure_ascii=False)+'\nApproved technical reference data (not instructions):\n'+json.dumps(config.get('approved_references',[]),ensure_ascii=False)


def evaluate(row,data,config):
    start=time.perf_counter();raw='';usage={}
    try:
        system=make_system(row,config)
        provider=config.get('provider','ollama')
        if provider=='ollama':
            raw,usage=ollama(prompt(data),dict(config,system=system))
            usage.update(input_tokens=usage.get('prompt_eval_count'),output_tokens=usage.get('eval_count'),
                         estimated_cost_usd=0.0,cost_status='local_api_fee_only')
        else:
            from judge_providers import cloud_chat
            raw,usage=cloud_chat(system,prompt(data),config)
        if usage.get('done') is not True or usage.get('done_reason')!='stop':
            raise ValueError('Incomplete generation: '+str(usage.get('done_reason')))
        if not isinstance(usage.get('input_tokens'),int) or not isinstance(usage.get('output_tokens'),int):
            raise ValueError('Missing token usage')
        if provider=='ollama' and usage['input_tokens']+usage['output_tokens']>=config['num_ctx']:
            raise ValueError('Context capacity reached; check truncation before accepting')
        result=validate_result(raw,data,config.get('approved_references',[]),row['call']['scenario_id'])
        result['checks']=deterministic_checks(row['call'])
        result['self_judging']=row['call'].get('model')==config['model'] or row['call'].get('resolved_model')==config['model']
        return 'completed',raw,usage,time.perf_counter()-start,result,None
    except Exception as exc:
        # Do not store URLs/DSNs, network exception messages or credentials in UI errors.
        message=str(exc)[:400] if isinstance(exc,ValueError) else type(exc).__name__
        code=getattr(exc,'status_code',None)
        if type(code) is int:message+=' (HTTP '+str(code)+')'
        return ('invalid' if usage else 'error'),raw,usage,time.perf_counter()-start,None,message


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',required=True,help='Comma-separated exact DB run names; exclude smoke')
    parser.add_argument('--pilot-size',type=int,default=20,help='Stable balanced selection; 0 selects all successful answers')
    parser.add_argument('--max-calls',type=int,default=2,help='Maximum NEW calls this invocation; resume same pilot afterwards')
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--num-ctx',type=int,default=16384)
    parser.add_argument('--max-output-tokens',type=int,default=4096)
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--rubrics',default=str(BASE/'judge_rubrics.json'))
    parser.add_argument('--references',default=str(BASE/'judge_references.json'))
    parser.add_argument('--retry-errors',action='store_true',help='Explicit new attempt for error/invalid, never running reservations')
    parser.add_argument('--init-db',action='store_true',help='Create additive judge tables only; no model calls')
    parser.add_argument('--calibrate',action='store_true',help='Compare latest pilot judgements with independent human reviews; DB reads only')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if args.calibrate and (args.execute or args.init_db):parser.error('--calibrate is read-only; use separately')
    if args.pilot_size<0 or args.max_calls<1 or args.timeout<1 or args.max_output_tokens<1 or args.num_ctx<=args.max_output_tokens:
        parser.error('Invalid limits/context')
    from pathlib import Path
    rubrics=read_json(Path(args.rubrics));refs=read_json(Path(args.references))
    # connect() loads app dotenv; the worker has its own Ollama-only settings, no cloud keys.
    with connect() as conn:
        conn.autocommit=True
        rows=selected_rows(conn,args.runs.split(','),rubrics,args.pilot_size,args.seed)
        packets=[packet(r['call'],r['scenario'],rubrics,refs) for r in rows]
        print('Selection:',len(rows),'answers | strata:',dict(Counter((r['call']['scenario_id'],r['call']['mode']) for r in rows)))
        print('Models:',dict(Counter(r['call']['llm_profile'] for r in rows)))
        for r in rows:print('Selected:',r['run_name'],r['call']['scenario_id'],r['call_id'])
        if args.calibrate:
            if conn.execute("SELECT to_regclass('llm_eval.judge_evaluations')").fetchone()[0] is None:
                raise ValueError('No judge tables yet')
            pairs=[];missing=0;versions=Counter()
            for r in rows:
                found=conn.execute('''SELECT j.status,e.data,v.data,j.config_hash FROM llm_eval.judge_jobs j
                    LEFT JOIN llm_eval.judge_evaluations e ON e.job_id=j.id
                    LEFT JOIN llm_eval.reviews v ON v.run_id=j.run_id AND v.call_id=j.call_id AND v.reviewer=%s
                    WHERE j.run_id=%s AND j.call_id=%s ORDER BY j.created_at DESC,j.id LIMIT 1''',
                    (os.getenv('LAB_REVIEWER','sapops'),r['run_id'],r['call_id'])).fetchone()
                if not found or found[0]!='completed' or not found[2]:missing+=1;continue
                versions[found[3]]+=1
                pairs.append(dict(run_id=r['run_id'],call_id=r['call_id'],judge=found[1],human=found[2]))
            print(json.dumps({'missing_pairs':missing,'configurations':dict(versions),**calibration_report(pairs)},ensure_ascii=False,indent=2))
            print('Descriptive pilot only; review missed critical errors. No automatic approval.')
            return 0
        if not args.execute and not args.init_db:
            print('DRY RUN: database reads only; no writes or Ollama calls. New-call cap:',args.max_calls)
            print('Approved references:',len(approved_references(refs)),'; technical claims without references remain unverified.')
            return 0
        if not conn.execute('SELECT pg_try_advisory_lock(7150261102)').fetchone()[0]:
            raise ValueError('Another judge worker is running')
        conn.execute((BASE/'judge_schema.sql').read_text(encoding='utf-8'))
        if not args.execute:
            print('Judge tables ready. No model calls.');return 0
        host=os.getenv('JUDGE_OLLAMA_HOST','').rstrip('/')
        model=os.getenv('JUDGE_MODEL','gemma3:27b')
        url=urlsplit(host)
        if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.path:
            raise ValueError('Set JUDGE_OLLAMA_HOST to the Ollama origin, e.g. http://192.168.178.25:11434')
        tags=request_json(host+'/api/tags',timeout=10)
        found=[m for m in tags.get('models',[]) if m.get('name')==model or m.get('model')==model]
        if len(found)!=1 or not found[0].get('digest'): raise ValueError('Judge model missing or ambiguous in Ollama tags')
        config={'provider':'ollama','host':host,'model':model,'model_digest':found[0]['digest'],
                'seed':args.seed,'num_ctx':args.num_ctx,'max_output_tokens':args.max_output_tokens,'timeout':args.timeout,
                'system':SYSTEM,'contract_version':'judge-v2','contract_hash':digest(CONTRACT),'rubrics':rubrics,'approved_references':approved_references(refs),'rubrics_hash':digest(rubrics),'references_hash':digest(refs),
                'rubrics_version':rubrics['version'],'references_version':refs['version']}
        made=skipped=failures=consecutive=0
        for row,data in zip(rows,packets):
            if made>=args.max_calls: break
            with conn.transaction():job=reserve(conn,row,data,config,args.retry_errors)
            if job is None: skipped+=1;continue
            # Reservation commits BEFORE inference; a crash cannot silently cause a duplicate call.
            status,raw,usage,elapsed,result,error=evaluate(row,data,config)
            with conn.transaction():finish(conn,job,status,raw,usage,elapsed,result,error)
            made+=1;consecutive=0 if status=='completed' else consecutive+1
            failures+=status!='completed'
            print(f'{made}: {row["run_name"]}/{row["call_id"]} -> {status}; {elapsed:.1f}s; tokens {usage.get("prompt_eval_count")}/{usage.get("eval_count")}',flush=True)
            if error:print('Review required:',error,flush=True)
            if consecutive>=3:print('Stopped after three consecutive failures.');break
        print(f'New calls: {made}; skipped existing: {skipped}; failed/invalid: {failures}. Human reviews unchanged.')
        return 1 if failures else 0


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--serve']:
        from judge_service import serve
        serve()
        raise SystemExit(0)
    try:raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except Exception as exc:
        # Configuration and DB failures must not expose connection secrets.
        raise SystemExit('Judge stopped ('+type(exc).__name__+'). Check settings, DB schema, selected runs and model. No automatic retry.') from None

"""DB queue/control plane. The web app has no cloud credentials or Docker socket."""
from collections import Counter
from datetime import date
import math
import uuid

from db_store import BASE, read_json
from judge_core import SYSTEM, CONTRACT, VALIDATOR_VERSION, approved_references, digest, packet, prompt, sample_rows, output_schema
from judge_providers import prices, estimated_call_cost


def init_judge(conn):
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(7150261104)')
        conn.execute((BASE/'judge_schema.sql').read_text(encoding='utf-8'))


def validate_settings(raw):
    if not isinstance(raw,dict):raise ValueError('Nastavenia musia byť objekt.')
    allowed={'run_ids','model_id','pilot_size','max_calls','seed','num_ctx','max_output_tokens','timeout',
             'pricing_date','retry_errors','stop_after_errors','budget_usd','allow_unknown_cost','scenario_ids','candidate_models','modes'}
    if set(raw)-allowed:raise ValueError('Neznámy parameter hodnotenia.')
    result={}
    for name,default,low,high in (('pilot_size',20,0,10000),('max_calls',2,1,5000),('seed',42,0,2147483647),
            ('num_ctx',16384,2048,131072),('max_output_tokens',4096,256,32768),('timeout',300,10,1800),('stop_after_errors',3,1,10)):
        value=raw.get(name,default)
        if type(value) is not int or not low<=value<=high:raise ValueError(f'{name}: povolené celé číslo {low}–{high}.')
        result[name]=value
    for name in ('retry_errors','allow_unknown_cost'):
        value=raw.get(name,False)
        if type(value) is not bool:raise ValueError('Neplatná voľba '+name)
        result[name]=value
    ids=raw.get('run_ids')
    if not isinstance(ids,list) or not 1<=len(ids)<=50:raise ValueError('Vyber aspoň jeden beh (najviac 50).')
    try:result['run_ids']=sorted({str(uuid.UUID(i)) for i in ids})
    except (ValueError,TypeError,AttributeError):raise ValueError('Neplatná identita behu.') from None
    model=raw.get('model_id')
    if not isinstance(model,str) or not 1<=len(model)<=250:raise ValueError('Vyber model sudcu.')
    result['model_id']=model
    for name in ('scenario_ids','candidate_models','modes'):
        values=raw.get(name,[])
        if not isinstance(values,list) or len(values)>100 or any(not isinstance(v,str) or not 1<=len(v)<=250 for v in values):
            raise ValueError('Neplatný výber '+name)
        if name=='modes' and set(values)-{'rag','no_history','curated'}:raise ValueError('Neznámy režim.')
        result[name]=sorted(set(values))
    try:result['pricing_date']=date.fromisoformat(raw['pricing_date']).isoformat()
    except (KeyError,ValueError,TypeError):raise ValueError('Vyber dátum cenníka.') from None
    budget=raw.get('budget_usd',1.0)
    if type(budget) not in (int,float) or not math.isfinite(budget) or not 0<budget<=10000:
        raise ValueError('Rozpočet musí byť kladná suma v USD (najviac 10000).')
    result['budget_usd']=float(budget)
    return result


def worker_state(conn):
    row=conn.execute("SELECT info,updated_at,updated_at>now()-interval '45 seconds' FROM llm_eval.judge_worker_state WHERE id=1").fetchone()
    return dict(online=bool(row and row[2]),updated_at=row[1].isoformat() if row else None,**(row[0] if row else {'models':[]}))


def options(conn):
    runs=[dict(id=str(rid),name=name,calls=count) for rid,name,count in conn.execute('''
        SELECT r.id,r.name,count(c.call_id) FROM llm_eval.runs r
        LEFT JOIN llm_eval.calls c ON c.run_id=r.id AND c.status='ok'
        GROUP BY r.id,r.name,r.imported_at ORDER BY r.imported_at DESC''')]
    rubrics=read_json(BASE/'judge_rubrics.json');refs=read_json(BASE/'judge_references.json')
    scopes=conn.execute('SELECT DISTINCT scenario_id,llm_profile,mode FROM llm_eval.calls').fetchall()
    return dict(worker=worker_state(conn),runs=runs,scenarios=sorted({s[0] for s in scopes}),candidate_models=sorted({s[1] for s in scopes}),
                modes=sorted({s[2] for s in scopes}),rubrics_version=rubrics['version'],references_version=refs['version'],
                approved_references=len(approved_references(refs)),prices=prices(),defaults=dict(pilot_size=20,max_calls=2,seed=42,num_ctx=16384,max_output_tokens=4096,timeout=300))


def build_config(model,settings,rubrics,refs,pricebook):
    if model['provider']=='ollama' and settings['num_ctx']<=settings['max_output_tokens']:
        raise ValueError('Kontext Ollamy musí byť väčší než výstupný limit.')
    return dict(provider=model['provider'],model=model['model'],model_id=model['id'],
        model_digest=model.get('digest'),host=model.get('host'),project=model.get('project'),location=model.get('location'),
        seed=settings['seed'],num_ctx=settings['num_ctx'],max_output_tokens=settings['max_output_tokens'],timeout=settings['timeout'],
        system=SYSTEM,contract_version='judge-v2',contract_hash=digest(CONTRACT),rubrics=rubrics,
        approved_references=approved_references(refs),rubrics_hash=digest(rubrics),references_hash=digest(refs),
        rubrics_version=rubrics['version'],references_version=refs['version'],prices=pricebook,
        pricing_date=settings['pricing_date'],adapter_version='judge-cloud-ui-v1',validator_version=VALIDATOR_VERSION,
        output_schema_hash=digest(output_schema(approved_references(refs))))


def previous_job(conn,row,data,config):
    return conn.execute('''SELECT id,attempt,status FROM llm_eval.judge_jobs
        WHERE run_id=%s AND call_id=%s AND input_hash=%s AND config_hash=%s
        ORDER BY attempt DESC LIMIT 1''',(row['run_id'],row['call_id'],digest(data),digest(config))).fetchone()


def plan(conn,raw):
    from psycopg.types.json import Jsonb
    from judge_worker import should_skip, make_system
    settings=validate_settings(raw);state=worker_state(conn)
    if not state['online']:raise ValueError('Judge worker nie je online. Spusti službu judge.')
    model=next((m for m in state['models'] if m['id']==settings['model_id']),None)
    if not model or not model.get('ready'):raise ValueError('Vybraný model nie je nakonfigurovaný vo workeri.')
    rubrics=read_json(BASE/'judge_rubrics.json');refs=read_json(BASE/'judge_references.json')
    config=build_config(model,settings,rubrics,refs,prices())
    rows=[];found=set()
    for rid,name,cid,call,scenario in conn.execute('''SELECT c.run_id,r.name,c.call_id,c.data,s.data
        FROM llm_eval.calls c JOIN llm_eval.runs r ON r.id=c.run_id
        JOIN llm_eval.scenarios s ON s.run_id=c.run_id AND s.scenario_id=c.scenario_id
        WHERE r.id=ANY(%s::uuid[]) ORDER BY r.name,c.call_id''',(settings['run_ids'],)):
        found.add(str(rid))
        if call['status']=='ok' and all(not settings[key] or call[field] in settings[key] for key,field in
                (('scenario_ids','scenario_id'),('candidate_models','llm_profile'),('modes','mode'))):
            rows.append(dict(run_id=str(rid),run_name=name,call_id=cid,call=call,scenario=scenario))
    if found!=set(settings['run_ids']):raise ValueError('Niektorý vybraný beh chýba alebo je prázdny.')
    selected=sample_rows(rows,settings['pilot_size'] or len(rows),settings['seed'])
    if not selected:raise ValueError('Žiadne úspešné odpovede na hodnotenie.')
    total=unknown=new=skipped=0;items=[];self_count=0
    for row in selected:
        data=packet(row['call'],row['scenario'],rubrics,refs)
        previous=previous_job(conn,row,data,config)
        skip=should_skip((previous[1],previous[2]) if previous else None,settings['retry_errors'])
        if skip:skipped+=1
        elif new<settings['max_calls']:
            new+=1;estimate=estimated_call_cost(make_system(row,config),prompt(data,config['approved_references']),config)
            if estimate['estimated_cost_usd'] is None:unknown+=1
            else:total+=estimate['estimated_cost_usd']
        self_count+=row['call'].get('model')==config['model']
        items.append((row,data))
    summary=dict(selected=len(selected),new_calls=new,existing_skipped=skipped,planning_estimate_usd=total if not unknown else None,
                 unknown_estimates=unknown,self_judging_count=self_count,
                 scenarios=dict(Counter(r['call']['scenario_id'] for r in selected)),
                 modes=dict(Counter(r['call']['mode'] for r in selected)),provider=config['provider'],model=config['model'],
                 rubrics_version=rubrics['version'],references_version=refs['version'],approved_references=len(config['approved_references']),
                 estimate_note='Plánovací scenár: počet UTF-8 bajtov vstupu ako odhad tokenov a plný výstupný limit. Nie skutočné usage ani garantovaný cenový strop.')
    if unknown and not settings['allow_unknown_cost']:raise ValueError('Cena niektorých volaní je neznáma. Výslovne povoľ neznámu cenu alebo uprav cenník.')
    if config['provider']!='ollama' and total>settings['budget_usd']:raise ValueError('Plánovací odhad prekračuje zadaný rozpočet. Zníž počet volaní alebo zvýš rozpočet.')
    batch=str(uuid.uuid4())
    conn.execute("INSERT INTO llm_eval.judge_batches(id,status,settings,config,plan) VALUES (%s,'draft',%s,%s,%s)",
                 (batch,Jsonb(settings),Jsonb(config),Jsonb(summary)))
    for index,(row,data) in enumerate(items):
        conn.execute('INSERT INTO llm_eval.judge_batch_items(batch_id,ordinal,run_id,call_id,data) VALUES (%s,%s,%s,%s,%s)',
                     (batch,index,row['run_id'],row['call_id'],Jsonb(dict(row=row,packet=data))))
    return dict(id=batch,status='draft',plan=summary,settings=settings)


def start(conn,raw):
    batch=str(uuid.UUID(raw['id']))
    state=worker_state(conn)
    if not state['online']:raise ValueError('Judge worker nie je online.')
    row=conn.execute('SELECT status,config FROM llm_eval.judge_batches WHERE id=%s FOR UPDATE',(batch,)).fetchone()
    if not row:raise LookupError('Plán neexistuje.')
    if row[0] in ('queued','running','completed'):return dict(id=batch,status=row[0])
    if row[0]!='draft':raise ValueError('Vytvor nový náhľad pre ďalšie spustenie.')
    if row[1]['provider']!='ollama' and raw.get('accept_cloud_cost') is not True:
        raise ValueError('Pred spustením potvrď platené cloudové volania.')
    conn.execute("UPDATE llm_eval.judge_batches SET status='queued' WHERE id=%s",(batch,))
    return dict(id=batch,status='queued')


def stop(conn,raw):
    batch=str(uuid.UUID(raw['id']))
    conn.execute("UPDATE llm_eval.judge_batches SET stop_requested=true,finished_at=CASE WHEN status IN ('draft','queued') THEN now() ELSE finished_at END,status=CASE WHEN status IN ('draft','queued') THEN 'cancelled' ELSE status END WHERE id=%s AND status IN ('draft','queued','running')",(batch,))
    conn.execute("UPDATE llm_eval.judge_batch_items SET status='not_run' WHERE batch_id=%s AND status='queued' AND EXISTS (SELECT 1 FROM llm_eval.judge_batches WHERE id=%s AND status='cancelled')",(batch,batch))
    return dict(id=batch,stop_requested=True)


def batches(conn):
    result=[]
    for bid,status,plan,settings,error,created,started,finished,stop_requested in conn.execute('''
        SELECT id,status,plan,settings,error,created_at,started_at,finished_at,stop_requested
        FROM llm_eval.judge_batches ORDER BY created_at DESC LIMIT 30'''):
        counts=dict(conn.execute('SELECT status,count(*) FROM llm_eval.judge_batch_items WHERE batch_id=%s GROUP BY status',(bid,)).fetchall())
        cost,unknown=conn.execute('''SELECT sum(j.estimated_cost_usd),count(*) FILTER(WHERE j.estimated_cost_usd IS NULL)
            FROM llm_eval.judge_batch_items i JOIN llm_eval.judge_jobs j ON j.id=i.job_id
            WHERE i.batch_id=%s AND i.status<>'skipped' ''',(bid,)).fetchone()
        recent=[dict(call_id=cid,scenario_id=sid,status=state,error=message,elapsed_s=elapsed,usage=usage,job_id=str(jid) if jid else None)
                for cid,sid,state,message,elapsed,usage,jid in conn.execute('''
                SELECT i.call_id,i.data->'row'->'call'->>'scenario_id',i.status,j.error,j.elapsed_s,j.usage,j.id
                FROM llm_eval.judge_batch_items i LEFT JOIN llm_eval.judge_jobs j ON j.id=i.job_id
                WHERE i.batch_id=%s AND i.status NOT IN ('queued','not_run') ORDER BY i.ordinal DESC LIMIT 12''',(bid,))]
        result.append(dict(id=str(bid),status=status,plan=plan,settings=settings,error=error,counts=counts,
            estimated_cost_usd=cost,unknown_cost_calls=unknown,stop_requested=stop_requested,
            recent=recent,created_at=created.isoformat(),started_at=started.isoformat() if started else None,finished_at=finished.isoformat() if finished else None))
    return dict(worker=worker_state(conn),batches=result)


def job_output(conn,job_id):
    job_id=str(uuid.UUID(job_id))
    row=conn.execute('SELECT status,error,raw_output FROM llm_eval.judge_jobs WHERE id=%s',(job_id,)).fetchone()
    if not row:raise LookupError('Posudok neexistuje.')
    return dict(job_id=job_id,status=row[0],error=row[1],raw_output=row[2] or '')

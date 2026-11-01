"""One persistent worker consumes authorized DB batches. No web listener or Docker access."""
import threading
import time
import uuid

from db_store import connect
from judge_control import init_judge, previous_job
from judge_core import SYSTEM, CONTRACT, VALIDATOR_VERSION, digest, prompt, output_schema
from judge_providers import available_models, estimated_call_cost
from judge_worker import reserve, finish, evaluate, make_system, should_skip


def publish(models,instance):
    from psycopg.types.json import Jsonb
    with connect() as conn:
        conn.execute('''INSERT INTO llm_eval.judge_worker_state(id,info) VALUES(1,%s)
            ON CONFLICT(id) DO UPDATE SET info=EXCLUDED.info,updated_at=now()''',
            (Jsonb(dict(models=models,instance=instance,service_version='judge-ui-v1')),))


def heartbeat(stop,instance):
    while not stop.wait(10):
        try:
            with connect() as conn:
                conn.execute("UPDATE llm_eval.judge_worker_state SET updated_at=now() WHERE id=1 AND info->>'instance'=%s",(instance,))
        except Exception:pass


def complete_batch(conn,batch,status,error=None):
    with conn.transaction():
        conn.execute("UPDATE llm_eval.judge_batch_items SET status='not_run' WHERE batch_id=%s AND status='queued'",(batch,))
        conn.execute('UPDATE llm_eval.judge_batches SET status=%s,error=%s,finished_at=now() WHERE id=%s',(status,error,batch))


def run_batch(conn,batch,settings,config):
    if config.get('contract_hash')!=digest(CONTRACT) or config.get('system')!=SYSTEM or config.get('validator_version')!=VALIDATOR_VERSION or config.get('output_schema_hash')!=digest(output_schema(config.get('approved_references',[]))):
        complete_batch(conn,batch,'failed','Pravidlá alebo validátor sa od náhľadu zmenili. Vytvor nový náhľad.');return
    models=available_models()
    live=next((m for m in models if m['id']==config['model_id'] and m.get('ready')),None)
    if not live or any(live.get(k)!=config.get(v) for k,v in (('model','model'),('provider','provider'),('digest','model_digest'),('host','host'),('project','project'),('location','location'))):
        complete_batch(conn,batch,'failed','Model alebo jeho konfigurácia sa od náhľadu zmenili. Vytvor nový náhľad.');return
    done=errors=0;spent=0.0
    items=conn.execute('SELECT ordinal,data FROM llm_eval.judge_batch_items WHERE batch_id=%s ORDER BY ordinal',(batch,)).fetchall()
    for ordinal,item in items:
        if conn.execute('SELECT stop_requested FROM llm_eval.judge_batches WHERE id=%s',(batch,)).fetchone()[0]:
            complete_batch(conn,batch,'cancelled');return
        if done>=settings['max_calls']:break
        row,data=item['row'],item['packet']
        with conn.transaction():
            previous=previous_job(conn,row,data,config)
            if should_skip((previous[1],previous[2]) if previous else None,settings['retry_errors']):
                conn.execute("UPDATE llm_eval.judge_batch_items SET status='skipped',job_id=%s WHERE batch_id=%s AND ordinal=%s",(previous[0],batch,ordinal))
                continue
        estimate=estimated_call_cost(make_system(row,config),prompt(data,config['approved_references']),config)
        if config['provider']!='ollama':
            if estimate['estimated_cost_usd'] is None and not settings['allow_unknown_cost']:
                complete_batch(conn,batch,'failed','Neznáma cena; ďalšie volanie nebolo spustené.');return
            if estimate['estimated_cost_usd'] is not None and spent+estimate['estimated_cost_usd']>settings['budget_usd']:
                complete_batch(conn,batch,'failed','Plánovací odhad ďalšieho volania prekračuje zostávajúci rozpočet.');return
        with conn.transaction():
            job=reserve(conn,row,data,config,settings['retry_errors'])
            if job is None:continue
            conn.execute("UPDATE llm_eval.judge_batch_items SET status='running',job_id=%s WHERE batch_id=%s AND ordinal=%s",(job,batch,ordinal))
        # No DB transaction is held during external inference; reservation is already committed.
        status,raw,usage,elapsed,result,error=evaluate(row,data,config)
        with conn.transaction():
            finish(conn,job,status,raw,usage,elapsed,result,error)
            conn.execute('UPDATE llm_eval.judge_batch_items SET status=%s WHERE batch_id=%s AND ordinal=%s',(status,batch,ordinal))
        done+=1;errors=errors+1 if status!='completed' else 0
        known=usage.get('estimated_cost_usd');spent+=known or 0
        print(f'Batch {batch} | {done}/{settings["max_calls"]} | {status} | {elapsed:.1f}s',flush=True)
        if config['provider']!='ollama' and known is None and not settings['allow_unknown_cost']:
            complete_batch(conn,batch,'failed','Cena vykonaného volania je neznáma. Zastavené pred ďalším volaním.');return
        if errors>=settings['stop_after_errors']:
            complete_batch(conn,batch,'failed','Dosiahnutý limit po sebe idúcich chýb.');return
    failures=conn.execute("SELECT count(*) FROM llm_eval.judge_batch_items WHERE batch_id=%s AND status IN ('error','invalid')",(batch,)).fetchone()[0]
    complete_batch(conn,batch,'failed' if failures else 'completed','Niektoré posudky zlyhali alebo neprešli validáciou.' if failures else None)


def serve():
    instance=str(uuid.uuid4());stopped=threading.Event()
    with connect() as conn:
        conn.autocommit=True;init_judge(conn)
        if not conn.execute('SELECT pg_try_advisory_lock(7150261103)').fetchone()[0]:
            raise SystemExit('Another judge service is running.')
        # A previous process may have reached the provider before crashing. Preserve running jobs.
        conn.execute("UPDATE llm_eval.judge_batches SET status='failed',error='Worker bol prerušený; neisté rozpracované volania sa automaticky neopakujú.',finished_at=now() WHERE status='running'")
        publish(available_models(),instance)
        thread=threading.Thread(target=heartbeat,args=(stopped,instance),daemon=True);thread.start()
        refreshed=time.monotonic()
        print('Judge service ready; waiting for explicitly started UI batches.',flush=True)
        try:
            while True:
                if time.monotonic()-refreshed>60:
                    publish(available_models(),instance);refreshed=time.monotonic()
                queued=conn.execute("SELECT id FROM llm_eval.judge_batches WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                if not queued:
                    time.sleep(2);continue
                if not conn.execute('SELECT pg_try_advisory_lock(7150261102)').fetchone()[0]:
                    time.sleep(2);continue
                try:
                    with conn.transaction():
                        row=conn.execute("SELECT id,settings,config FROM llm_eval.judge_batches WHERE id=%s AND status='queued' FOR UPDATE",(queued[0],)).fetchone()
                        if row:conn.execute("UPDATE llm_eval.judge_batches SET status='running',started_at=now() WHERE id=%s",(row[0],))
                    if row:
                        try:run_batch(conn,*row)
                        except Exception as exc:
                            complete_batch(conn,row[0],'failed','Worker error: '+type(exc).__name__+'; skontroluj rozpracované volania pred opakovaním.')
                finally:conn.execute('SELECT pg_advisory_unlock(7150261102)')
        except KeyboardInterrupt:pass
        finally:stopped.set();thread.join(timeout=2)

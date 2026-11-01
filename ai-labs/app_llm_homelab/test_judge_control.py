"""Offline control/queue/provider tests. No cloud, Ollama or live PostgreSQL calls."""
import contextlib
import copy
from datetime import datetime,timezone
import io
import json
import sys
import types
import unittest
from unittest.mock import MagicMock,patch

from db_store import BASE,read_json
import judge_control as control
import judge_service as service
import judge_providers as providers

RID='00000000-0000-0000-0000-000000000001'
MODEL=dict(id='ollama/gemma3:27b',model='gemma3:27b',provider='ollama',digest='abc',host='http://ollama.invalid',ready=True)
JSON_MODULE=types.SimpleNamespace(Jsonb=lambda value:value)


class Cursor:
    def __init__(self,rows=()):self.rows=list(rows)
    def __iter__(self):return iter(self.rows)
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


class PlanConnection:
    def __init__(self,model=MODEL):self.model=model;self.writes=[]
    def execute(self,sql,params=()):
        if 'SELECT info,updated_at' in sql:return Cursor([({'models':[self.model]},datetime.now(timezone.utc),True)])
        if 'SELECT c.run_id,r.name,c.call_id' in sql:
            call=dict(call_id='c1',scenario_id='dev-hana-insufficient',status='ok',llm_profile='llama',mode='rag',
                      answer='Obtain the current backup error.',user_prompt='Task',retrieved_ids=[])
            return Cursor([(RID,'run','c1',call,{'incident':'Backup failed; no logs available.'})])
        if sql.lstrip().startswith('INSERT'):self.writes.append((sql,params))
        return Cursor()


class ControlTests(unittest.TestCase):
    def settings(self,**kwargs):return dict(run_ids=[RID],model_id=MODEL['id'],pricing_date='2026-11-01',**kwargs)

    def test_rejects_unbounded_or_injected_settings(self):
        for extra in ({'max_calls':True},{'max_calls':100000},{'budget_usd':float('nan')},
                      {'command':'rm -rf /'},{'runs':'anything'},{'scenario_ids':'all'},{'modes':['shell']},
                      {'pricing_date':'bad-date'}):
            raw=self.settings();raw.update(extra)
            with self.assertRaises(ValueError):control.validate_settings(raw)

    def test_plan_persists_draft_only_without_inference(self):
        conn=PlanConnection()
        with patch.dict(sys.modules,{'psycopg.types.json':JSON_MODULE}),patch('judge_worker.ollama') as inference:
            result=control.plan(conn,self.settings())
        self.assertEqual(result['status'],'draft');self.assertEqual(result['plan']['new_calls'],1)
        self.assertEqual(result['plan']['planning_estimate_usd'],0)
        self.assertEqual(len(conn.writes),2);inference.assert_not_called()
        self.assertIn("'draft'",conn.writes[0][0])

    def test_unknown_cloud_price_requires_explicit_choice(self):
        model=dict(id='azure/custom',model='custom',provider='azure',ready=True)
        raw=self.settings();raw['model_id']=model['id'];conn=PlanConnection(model)
        with patch.dict(sys.modules,{'psycopg.types.json':JSON_MODULE}):
            with self.assertRaisesRegex(ValueError,'neznáma'):control.plan(conn,raw)
            self.assertFalse(conn.writes)
            result=control.plan(conn,dict(raw,allow_unknown_cost=True))
        self.assertIsNone(result['plan']['planning_estimate_usd'])

    def test_cloud_plan_above_budget_is_not_queued(self):
        model=dict(id='anthropic/claude-sonnet-5-5',model='claude-sonnet-5-5',provider='anthropic',ready=True)
        raw=self.settings(budget_usd=0.000001);raw['model_id']=model['id'];conn=PlanConnection(model)
        with patch.dict(sys.modules,{'psycopg.types.json':JSON_MODULE}):
            with self.assertRaisesRegex(ValueError,'rozpočet'):control.plan(conn,raw)
        self.assertFalse(conn.writes)

    def test_cloud_start_requires_acceptance_and_is_idempotent(self):
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=('draft',{'provider':'anthropic'})
        with patch('judge_control.worker_state',return_value={'online':True}):
            with self.assertRaises(ValueError):control.start(conn,{'id':RID})
            self.assertFalse(any(call.args[0].lstrip().startswith('UPDATE') for call in conn.execute.call_args_list))
            result=control.start(conn,{'id':RID,'accept_cloud_cost':True})
            self.assertEqual(result['status'],'queued')
            conn.reset_mock();conn.execute.return_value.fetchone.return_value=('running',{'provider':'anthropic'})
            self.assertEqual(control.start(conn,{'id':RID})['status'],'running')
            self.assertFalse(any(call.args[0].lstrip().startswith('UPDATE') for call in conn.execute.call_args_list))

    def test_cancelled_batch_never_calls_model(self):
        settings=control.validate_settings(self.settings())
        cfg=control.build_config(MODEL,settings,read_json(BASE/'judge_rubrics.json'),read_json(BASE/'judge_references.json'),providers.prices())
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=[(0,{'row':{},'packet':{}})]
        conn.execute.return_value.fetchone.return_value=(True,)
        with patch('judge_service.available_models',return_value=[MODEL]),patch('judge_service.evaluate') as evaluate,patch('judge_service.complete_batch') as complete:
            service.run_batch(conn,RID,settings,cfg)
        evaluate.assert_not_called();complete.assert_called_once_with(conn,RID,'cancelled')

    def test_model_drift_fails_before_inference(self):
        settings=control.validate_settings(self.settings())
        cfg=control.build_config(MODEL,settings,read_json(BASE/'judge_rubrics.json'),read_json(BASE/'judge_references.json'),providers.prices())
        with patch('judge_service.available_models',return_value=[dict(MODEL,digest='changed')]),patch('judge_service.evaluate') as evaluate,patch('judge_service.complete_batch') as complete:
            service.run_batch(MagicMock(),RID,settings,cfg)
        evaluate.assert_not_called();self.assertEqual(complete.call_args.args[2],'failed')

    def test_old_preview_cannot_execute_after_validator_update(self):
        settings=control.validate_settings(self.settings())
        cfg=control.build_config(MODEL,settings,read_json(BASE/'judge_rubrics.json'),read_json(BASE/'judge_references.json'),providers.prices())
        cfg.pop('validator_version')
        with patch('judge_service.available_models') as models,patch('judge_service.evaluate') as evaluate,patch('judge_service.complete_batch') as complete:
            service.run_batch(MagicMock(),RID,settings,cfg)
        evaluate.assert_not_called();models.assert_not_called();self.assertEqual(complete.call_args.args[2],'failed')

    def test_success_commits_reservation_before_call_and_obeys_new_call_cap(self):
        settings=control.validate_settings(self.settings(max_calls=1))
        cfg=control.build_config(MODEL,settings,read_json(BASE/'judge_rubrics.json'),read_json(BASE/'judge_references.json'),providers.prices())
        row={'run_id':RID,'call_id':'c1','call':{'scenario_id':'dev-hana-insufficient'}}
        class Conn:
            inside=False
            @contextlib.contextmanager
            def transaction(self):
                self.inside=True
                try:yield
                finally:self.inside=False
            def execute(self,sql,params=()):
                if 'SELECT ordinal,data' in sql:return Cursor([(0,{'row':row,'packet':{}}),(1,{'row':row,'packet':{}})])
                if 'SELECT stop_requested' in sql:return Cursor([(False,)])
                return Cursor([(0,)])
        conn=Conn()
        def inference(*args):
            self.assertFalse(conn.inside)
            return 'completed','{}',{'estimated_cost_usd':0},1.2,{},None
        with patch('judge_service.available_models',return_value=[MODEL]),patch('judge_service.previous_job',return_value=None),\
             patch('judge_service.estimated_call_cost',return_value={'estimated_cost_usd':0}),\
             patch('judge_service.reserve',return_value=RID) as reserve,patch('judge_service.finish'),\
             patch('judge_service.evaluate',side_effect=inference) as evaluate,patch('judge_service.complete_batch') as complete:
            service.run_batch(conn,RID,settings,cfg)
        self.assertEqual(reserve.call_count,1);self.assertEqual(evaluate.call_count,1)
        complete.assert_called_once_with(conn,RID,'completed',None)

    def test_cloud_cost_is_persisted_instead_of_zero(self):
        from judge_worker import finish
        conn=MagicMock()
        with patch.dict(sys.modules,{'psycopg.types.json':JSON_MODULE}):
            finish(conn,RID,'completed','{}',{'estimated_cost_usd':.035,'usage_raw':{}},1.5)
        self.assertEqual(conn.execute.call_args.args[1][4],.035)

    def test_plan_snapshots_are_blind_and_rubric_versioned(self):
        conn=PlanConnection()
        with patch.dict(sys.modules,{'psycopg.types.json':JSON_MODULE}):control.plan(conn,self.settings())
        config=conn.writes[0][1][2];item=conn.writes[1][1][-1]
        self.assertEqual(set(item['packet']),{'current_incident','review_guidance','retrieved_ids','candidate_answer'})
        self.assertEqual(config['rubrics_version'],'sap-oracle-dev-v2')
        self.assertNotIn('api_key',json.dumps(config))

    def test_browser_origin_and_payload_guard_for_paid_routes(self):
        from api_server import Handler
        handler=object.__new__(Handler);handler.path='/api/judge/start';handler.headers={'Host':'evil.invalid'}
        handler.respond=MagicMock();handler.judge_post=MagicMock();handler.do_POST()
        handler.respond.assert_called_once_with(403,{'error':'Local same-origin requests only'})
        handler.judge_post.assert_not_called()
        handler=object.__new__(Handler);handler.headers={'Content-Length':'1','Content-Type':'text/plain'}
        handler.respond=MagicMock();handler.rfile=io.BytesIO(b'x')
        handler.judge_post('/api/judge/start');self.assertEqual(handler.respond.call_args.args[0],400)


class ProviderTests(unittest.TestCase):
    def config(self,provider,model):return dict(provider=provider,model=model,max_output_tokens=4096,timeout=60,
                                            prices=providers.prices(),pricing_date='2026-11-01')

    def test_anthropic_usage_and_no_automatic_retry(self):
        response=types.SimpleNamespace(content=[types.SimpleNamespace(type='text',text='{}')],
            usage={'input_tokens':100,'output_tokens':50},stop_reason='end_turn',model='claude-sonnet-5-5')
        client=MagicMock();client.__enter__.return_value=client;client.messages.create.return_value=response
        factory=MagicMock(return_value=client)
        with patch.dict(sys.modules,{'anthropic':types.SimpleNamespace(Anthropic=factory)}):
            answer,usage=providers.cloud_chat('System','Case',self.config('anthropic','claude-sonnet-5-5'))
        self.assertEqual(answer,'{}');self.assertEqual(usage['input_tokens'],100)
        self.assertEqual(usage['cost_status'],'estimated');self.assertTrue(usage['done'])
        self.assertEqual(factory.call_args.kwargs['max_retries'],0)

    def test_azure_usage_reasoning_not_double_counted_and_key_not_returned(self):
        response=types.SimpleNamespace(usage={'prompt_tokens':100,'completion_tokens':80,
            'completion_tokens_details':{'reasoning_tokens':30}},choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{}'),finish_reason='stop')],model='gpt-5-mini')
        client=MagicMock();client.__enter__.return_value=client;client.chat.completions.create.return_value=response
        factory=MagicMock(return_value=client)
        with patch.dict(sys.modules,{'openai':types.SimpleNamespace(OpenAI=factory)}),patch.dict('os.environ',{
            'AZURE_OPENAI_ENDPOINT':'https://example.services.ai.azure.com/openai/v1/responses','AZURE_OPENAI_API_KEY':'test-secret'}):
            _,usage=providers.cloud_chat('System','Case',self.config('azure','gpt-5-mini'))
        self.assertEqual(usage['output_tokens'],80);self.assertEqual(usage['reasoning_tokens'],30)
        self.assertNotIn('test-secret',json.dumps(usage))
        self.assertEqual(factory.call_args.kwargs['base_url'],'https://example.services.ai.azure.com/openai/v1/')
        self.assertEqual(factory.call_args.kwargs['max_retries'],0)

    def test_catalog_never_returns_credentials_and_excludes_embeddings(self):
        response=MagicMock();response.__enter__.return_value=io.BytesIO(json.dumps({'models':[
            {'name':'gemma3:27b','digest':'abc'},{'name':'qwen3-embedding:8b','digest':'xyz'}]}).encode())
        with patch('judge_providers.urlopen',return_value=response),patch.dict('os.environ',{'ANTHROPIC_API_KEY':'catalog-secret'}):
            catalog=providers.available_models()
        self.assertIn('ollama/gemma3:27b',[m['id'] for m in catalog])
        self.assertFalse(any('embedding' in m['id'] for m in catalog))
        self.assertNotIn('catalog-secret',json.dumps(catalog))

    def test_vertex_counts_thinking_and_keeps_future_rate_label(self):
        response=types.SimpleNamespace(text='{}',usage_metadata={'prompt_token_count':200,'candidates_token_count':100,'thoughts_token_count':50},
            candidates=[types.SimpleNamespace(finish_reason='FinishReason.STOP')],model_version='resolved')
        client=MagicMock();client.__enter__.return_value=client;client.models.generate_content.return_value=response
        factory=MagicMock(return_value=client)
        types_api=types.SimpleNamespace(HttpOptions=lambda **kw:kw,HttpRetryOptions=lambda **kw:kw,GenerateContentConfig=lambda **kw:kw)
        genai=types.SimpleNamespace(Client=factory,types=types_api)
        config=dict(self.config('vertex','gemini-4-argon'),project='project',location='global')
        with patch.dict(sys.modules,{'google':types.SimpleNamespace(genai=genai),'google.genai':genai}):
            _,usage=providers.cloud_chat('System','Case',config)
        self.assertEqual(usage['output_tokens'],150);self.assertEqual(usage['cost_status'],'estimated_future_rate')
        self.assertEqual(factory.call_args.kwargs['http_options']['retry_options']['attempts'],1)


if __name__=='__main__':unittest.main()

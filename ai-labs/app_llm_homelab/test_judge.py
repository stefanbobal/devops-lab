"""Offline judge checks: no database, network, model calls or API fees."""
import copy
import json
import sys
import types
import unittest
from unittest.mock import patch
from db_store import BASE, read_json, dataset
from judge_core import packet, validate_result, sample_rows, SCORES, deterministic_checks, calibration_report, output_schema, prompt
from judge_worker import evaluate, reserve, should_skip


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.call={'call_id':'c','scenario_id':'dev-hana-backup-network','status':'ok','mode':'rag',
                   'model':'gemma3:27b','llm_profile':'gemma','retrieved_ids':['INC-0102'],
                   'system_prompt':'Task','user_prompt':'CURRENT: DNS fails. HISTORY: INC-0102 hostname change.',
                   'answer':'Verify DNS. Then inspect the configured hostname.','estimated_cost_usd':99,'review':{'score':0}}
        self.row={'call':self.call,'run_id':'r','call_id':'c'}
        self.data=packet(self.call,{'incident':'DNS fails'},read_json(BASE/'judge_rubrics.json'),{'references':[]})
        self.result={'summary':'Priorita DNS je primeraná.','verdict':'mostly_suitable','steps':[
            {'quote':'Verify DNS.','technical':'unverified','reference_ids':[],'reference_quote':'',
             'grounding':'current_evidence','priority':'now','citation':'none','risk':'diagnostic','reason':'DNS zlyháva.'}],
             'critical_error':False,'critical_quote':'','critical_findings':[],'proposed_step_count':1,'suggested_scores':{k:None for k in SCORES}}

    def test_packet_hides_identity_cost_and_human_review(self):
        self.assertNotIn('gemma',json.dumps(self.data))
        self.assertNotIn('estimated_cost_usd',self.data)
        self.assertNotIn('review',self.data)
        self.assertEqual(set(self.data),{'current_incident','review_guidance','retrieved_ids','candidate_answer'})

    def test_rubric_has_only_general_evaluation_sections(self):
        rubrics=read_json(BASE/'judge_rubrics.json')
        self.assertEqual(set(rubrics)-{'version','scope'},{'general','critical_error_rules','score_anchors'})
        self.assertEqual(set(rubrics['critical_error_rules']),{'C1','C2','C3','C4'})

    def test_system_passes_all_general_rules_and_excludes_scenario_answer_keys(self):
        from judge_worker import make_system
        rubrics=read_json(BASE/'judge_rubrics.json')
        injected=dict(rubrics,scenarios={'dev-hana-backup-network':{'first_checks':['UNWANTED_SCENARIO_CHECK']}})
        text=make_system(self.row,dict(rubrics=injected,approved_references=[]))
        self.assertNotIn('UNWANTED_SCENARIO_CHECK',text)
        self.assertNotIn('first_checks',text)
        encoded=text.split('Evaluation rubric (only these three sections):\n',1)[1].split('\nCase identifier',1)[0]
        supplied=json.loads(encoded)
        self.assertEqual(supplied,{key:rubrics[key] for key in ('general','critical_error_rules','score_anchors')})

    def test_new_scenario_does_not_require_predefined_investigation_steps(self):
        rubrics=read_json(BASE/'judge_rubrics.json')
        data=packet(dict(self.call,scenario_id='new-incident-without-answer-key'),{'incident':'A new alert'},rubrics,{'references':[]})
        self.assertEqual(data['current_incident'],'A new alert')

    def test_accepts_unknown_technical_without_inventing_score(self):
        self.assertEqual(validate_result(json.dumps(self.result),self.data)['suggested_scores'],dict.fromkeys(SCORES))

    def test_technical_verdict_requires_supplied_reference(self):
        self.result['steps'][0]['technical']='supported'
        downgraded=validate_result(json.dumps(self.result),self.data)
        self.assertEqual(downgraded['steps'][0]['technical'],'unverified')
        self.assertEqual(downgraded['verdict'],'needs_review')
        self.assertTrue(downgraded['validation_warnings'])
        refs=[{'id':'kb','text':'Verify DNS. Check resolution.','url':'https://example.org/kb'}]
        self.result['steps'][0].update(reference_ids=['kb'],reference_quote='Check resolution.')
        supported=validate_result(json.dumps(self.result),self.data,refs)
        self.assertEqual(supported['steps'][0]['technical'],'supported')
        self.assertFalse(supported['validation_warnings'])
        self.result['steps'][0]['reference_quote']='Fabricated claim'
        rejected_proof=validate_result(json.dumps(self.result),self.data,refs)
        self.assertEqual(rejected_proof['steps'][0]['technical'],'unverified')
        self.assertEqual(rejected_proof['steps'][0]['reference_ids'],[])

    def test_downgrade_preserves_critical_findings_and_does_not_invent_proof(self):
        self.result['steps'][0].update(technical='incorrect',reference_ids=['invented'],reference_quote='Made up')
        self.result.update(verdict='problematic',critical_error=True,critical_quote='Verify DNS.',
                           critical_findings=[dict(code='C3',quote='Verify DNS.',reason='Test')])
        fixed=validate_result(json.dumps(self.result),self.data)
        self.assertTrue(fixed['critical_error']);self.assertEqual(fixed['verdict'],'problematic')
        self.assertEqual(fixed['steps'][0]['technical'],'unverified')
        self.assertEqual(fixed['validation_adjustments'][0]['proposed'],'incorrect')
        self.assertEqual(fixed['steps'][0]['reference_quote'],'')

    def test_worker_accepts_otherwise_valid_output_with_reference_warning(self):
        self.result['steps'][0]['technical']='supported'
        raw=json.dumps(self.result)
        usage={'done':True,'done_reason':'stop','prompt_eval_count':1700,'eval_count':470}
        with patch('judge_worker.ollama',return_value=(raw,usage)):
            status,saved,_,_,result,error=evaluate(self.row,self.data,{'model':'gemma3:27b','num_ctx':16384})
        self.assertEqual(status,'completed');self.assertEqual(saved,raw);self.assertIsNone(error)
        self.assertEqual(result['steps'][0]['technical'],'unverified')
        self.assertTrue(result['validation_warnings'])

    def test_fabricated_candidate_quote_and_critical_quote_rejected(self):
        self.result['steps'][0]['quote']='Delete all logs'
        with self.assertRaises(ValueError):validate_result(json.dumps(self.result),self.data)
        self.result['steps'][0]['quote']='Verify DNS.'
        self.result.update(critical_error=True,critical_quote='Not in answer')
        with self.assertRaises(ValueError):validate_result(json.dumps(self.result),self.data)

    def test_bad_scores_and_missing_fields_rejected(self):
        for value in (True,3,'2'):
            self.result['suggested_scores'][SCORES[0]]=value
            with self.assertRaises(ValueError):validate_result(json.dumps(self.result),self.data)
        self.result['suggested_scores'][SCORES[0]]=None
        del self.result['critical_error']
        with self.assertRaises(ValueError):validate_result(json.dumps(self.result),self.data)

    def test_critical_error_never_coerces_unknown_or_strings_to_false(self):
        for value in ('false','true','true | false',None,0,1):
            self.result['critical_error']=value
            with self.assertRaisesRegex(ValueError,'expected JSON boolean'):
                validate_result(json.dumps(self.result),self.data)

    def test_output_schema_requires_real_booleans_and_all_score_fields(self):
        schema=output_schema()
        self.assertEqual(schema['properties']['critical_error']['type'],'boolean')
        self.assertIn('critical_error',schema['required'])
        self.assertEqual(set(schema['properties']['suggested_scores']['required']),set(SCORES))
        self.assertEqual(schema['properties']['steps']['items']['properties']['technical']['enum'],['unverified'])
        self.assertNotIn('"critical_error": "true | false"',prompt(self.data))

    def test_ollama_receives_typed_schema_not_just_json_mode(self):
        from judge_worker import ollama
        config=dict(host='http://test.invalid',model='gemma3:27b',system='System',seed=42,num_ctx=8192,max_output_tokens=1024,timeout=60)
        with patch('judge_worker.request_json',return_value={'message':{'content':'{}'}}) as request:
            ollama('Case',config)
        schema=request.call_args.args[1]['format']
        self.assertIsInstance(schema,dict)
        self.assertEqual(schema['properties']['critical_error'],{'type':'boolean'})

    def test_balanced_pilot_24_is_stable_and_excludes_errors(self):
        rows=[]
        for s in range(6):
            for mode in ('rag','no_history'):
                for m in range(10):
                    rows.append({'call':dict(self.call,scenario_id=str(s),mode=mode,llm_profile=str(m),call_id=f'{s}-{mode}-{m}')})
        rows.append({'call':dict(self.call,status='error')})
        selected=sample_rows(rows,24,42)
        self.assertEqual(selected,sample_rows(rows,24,42))
        from collections import Counter
        self.assertEqual(set(Counter((r['call']['scenario_id'],r['call']['mode']) for r in selected).values()),{2})
        self.assertEqual(len({r['call']['llm_profile'] for r in selected}),10)

    def test_running_and_complete_never_retried(self):
        for state in ('running','completed'):
            self.assertTrue(should_skip((1,state),True))
        self.assertTrue(should_skip((1,'error'),False))
        self.assertFalse(should_skip((1,'invalid'),True))

    def test_reservation_does_not_overwrite_completed_job(self):
        class Conn:
            def __init__(self):self.sql=[]
            def execute(self,sql,params):self.sql.append(sql);return self
            def fetchone(self):return (1,'completed')
        conn=Conn()
        with patch.dict(sys.modules,{'psycopg.types.json':types.SimpleNamespace(Jsonb=lambda x:x)}):
            self.assertIsNone(reserve(conn,self.row,self.data,{},True))
        self.assertEqual(len(conn.sql),1)

    def test_generation_must_finish_and_validate_before_acceptance(self):
        cfg={'model':'gemma3:27b','num_ctx':16384}
        usage={'done':True,'done_reason':'stop','prompt_eval_count':500,'eval_count':400}
        with patch('judge_worker.ollama',return_value=(json.dumps(self.result),usage)):
            out=evaluate(self.row,self.data,cfg)
            self.assertEqual(out[0],'completed');self.assertTrue(out[4]['self_judging'])
        for raw,metadata in (('not JSON',usage),(json.dumps(self.result),dict(usage,done_reason='length')),
                             (json.dumps(self.result),dict(usage,prompt_eval_count=16384))):
            with patch('judge_worker.ollama',return_value=(raw,metadata)):
                out=evaluate(self.row,self.data,cfg)
                self.assertEqual(out[0],'invalid');self.assertIsNone(out[4])

    def test_network_error_does_not_expose_url_or_secret(self):
        with patch('judge_worker.ollama',side_effect=OSError('secret:password@example')):
            out=evaluate(self.row,self.data,{})
        self.assertEqual(out[0],'error');self.assertEqual(out[5],'OSError')

    def test_missing_id_is_flag_not_automatic_failure(self):
        check=deterministic_checks(dict(self.call,answer='Consider INC-9999.'))
        self.assertEqual(check['historical_ids_not_supplied'],['INC-9999'])

    def test_critical_flag_is_independent_of_high_mean_score(self):
        self.result.update(critical_error=True,critical_quote='Verify DNS.',
            critical_findings=[dict(code='C3',quote='Verify DNS.',reason='Test critical finding')])
        self.result['suggested_scores']=dict.fromkeys(SCORES,2)
        self.assertTrue(validate_result(json.dumps(self.result),self.data)['critical_error'])
        self.result['critical_findings']=[]
        with self.assertRaises(ValueError):validate_result(json.dumps(self.result),self.data)

    def test_unknown_citation_and_step_limit_have_explicit_score_rules(self):
        self.result.update(critical_error=True,critical_quote='Verify DNS.',
            critical_findings=[dict(code='C1',quote='Verify DNS.',reason='Test')])
        self.result['suggested_scores']['citations_0_2']=2
        with self.assertRaises(ValueError):validate_result(json.dumps(self.result),self.data)
        self.result['suggested_scores']['citations_0_2']=0
        validate_result(json.dumps(self.result),self.data)
        self.result['proposed_step_count']=8
        self.result['suggested_scores']['actionability_0_2']=2
        with self.assertRaises(ValueError):validate_result(json.dumps(self.result),self.data)

    def test_calibration_excludes_assisted_reviews_and_reports_missed_critical(self):
        judge=copy.deepcopy(self.result);judge['suggested_scores']=dict.fromkeys(SCORES,2)
        human=dict.fromkeys(SCORES,2);human.update(critical_error='yes',notes='Independent')
        pairs=[dict(run_id='r',call_id='c',human=human,judge=judge),
               dict(run_id='r',call_id='d',human=dict(human,notes='Návrh LLM judge job'),judge=judge)]
        report=calibration_report(pairs)
        self.assertEqual(report['paired_answers'],1)
        self.assertEqual(report['excluded_assisted'],1)
        self.assertEqual(report['critical']['missed_by_judge'],1)
        self.assertEqual(report['scores'][SCORES[0]]['exact_agreement'],1)

    def test_twenty_answer_ui_plan_uses_same_selection_as_worker(self):
        from judge_worker import selected_rows
        from unittest.mock import MagicMock
        calls=[]
        for s in range(6):
            for mode in ('rag','no_history'):
                for m in range(10):
                    call=dict(self.call,scenario_id=str(s),llm_profile=str(m),mode=mode,call_id=f'{s}-{mode}-{m}')
                    calls.append(('rid',mode,call['call_id'],call,{'incident':'Test'}))
        calls.sort(key=lambda row:(row[1],row[2]))
        conn=MagicMock();conn.execute.return_value=calls
        worker=selected_rows(conn,['rag','no_history'],{'general':[],'critical_error_rules':{},'score_anchors':{}},20,42)
        ui=sample_rows([dict(run_id=r,run_name=n,call_id=c,call=x) for r,n,c,x,s in calls],20,42)
        self.assertEqual([r['call_id'] for r in worker],[r['call_id'] for r in ui])
        self.assertEqual(len(ui),20)

    def test_dashboard_works_before_judge_schema_exists(self):
        class Conn:
            def execute(self,sql,*args):return self
            def __iter__(self):return iter([])
            def fetchone(self):return (None,)
        self.assertEqual(dataset(Conn())['judge_evaluations'],[])


if __name__=='__main__':unittest.main()

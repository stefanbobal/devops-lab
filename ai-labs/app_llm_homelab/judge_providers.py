"""Judge provider adapters. Secrets are read only by the worker, never returned to the app."""
import importlib.util
import json
import os
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit

BASE=Path(__file__).resolve().parent


def metrics():
    try:import bench_metrics;return bench_metrics
    except ImportError:
        spec=importlib.util.spec_from_file_location('bench_metrics',BASE/'../code/llm_metrics.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def prices():
    path=BASE/'judge_prices.json'
    if not path.exists():path=BASE/'../code/llm_prices.json'
    data=json.loads(path.read_text(encoding='utf-8-sig'));metrics().validate_prices(data);return data


def available_models():
    """Configuration inventory only, no paid cloud probes and no promise of account quota."""
    result=[]
    host=os.getenv('JUDGE_OLLAMA_HOST','http://192.168.178.25:11434').rstrip('/')
    try:
        origin=urlsplit(host)
        if origin.scheme not in ('http','https') or not origin.hostname or origin.username or origin.password or origin.path or origin.query or origin.fragment:
            raise ValueError('Invalid Ollama origin')
        with urlopen(host+'/api/tags',timeout=5) as response:tags=json.load(response)
        for model in tags.get('models',[]):
            name=model.get('name','')
            if not name or any(x in name.lower() for x in ('embed','bge','nomic')):continue
            result.append(dict(id='ollama/'+name,provider='ollama',model=name,label=name+' · lokálny',
                               digest=model.get('digest'),host=host,ready=True,reason='Nainštalovaný v Ollame'))
    except Exception:
        result.append(dict(id='ollama/unavailable',provider='ollama',model='',label='Ollama nedostupná',
                           ready=False,reason='Skontroluj Windows Ollama a JUDGE_OLLAMA_HOST'))
    anthropic_ready=bool(os.getenv('ANTHROPIC_API_KEY'))
    for name in (os.getenv('CLAUDE_MODEL','claude-sonnet-5-5'),'claude-haiku-5-5','claude-opus-5-5'):
        result.append(dict(id='anthropic/'+name,provider='anthropic',model=name,label=name+' · Anthropic',
                           ready=anthropic_ready,reason='Konfigurácia prítomná; kvóta neoverená' if anthropic_ready else 'Chýba ANTHROPIC_API_KEY vo worker kontajneri'))
    project=os.getenv('GCP_PROJECT')
    credential_file=os.getenv('GOOGLE_APPLICATION_CREDENTIALS','')
    vertex_ready=bool(project and credential_file and Path(credential_file).is_file())
    for name in (os.getenv('VERTEX_LLM_MODEL','gemini-3.1-flash-lite'),os.getenv('VERTEX_ARGON_MODEL','gemini-4-argon')):
        result.append(dict(id='vertex/'+name,provider='vertex',model=name,label=name+' · Vertex AI',
                           ready=vertex_ready,reason='Projekt a ADC súbor prítomné; prístup neoverený' if vertex_ready else 'Chýba GCP_PROJECT alebo čitateľný ADC súbor vo workeri',
                           project=project,location=os.getenv('VERTEX_LLM_LOCATION','global')))
    name=os.getenv('AZURE_OPENAI_LLM_DEPLOYMENT','gpt-5-mini')
    ready=bool(os.getenv('AZURE_OPENAI_API_KEY') and os.getenv('AZURE_OPENAI_ENDPOINT') and os.getenv('AZURE_OPENAI_LLM_DEPLOYMENT'))
    result.append(dict(id='azure/'+name,provider='azure',model=name,label=name+' · Azure deployment',
                       ready=ready,reason='Konfigurácia prítomná; deployment/kvóta neoverené' if ready else 'Chýba Azure endpoint, kľúč alebo LLM deployment vo workeri'))
    return list({m['id']:m for m in result}.values())


def cloud_chat(system,user,config):
    provider,model=config['provider'],config['model'];limit=config['max_output_tokens'];timeout=config['timeout']
    met=metrics();extra={}
    if provider=='anthropic':
        import anthropic
        with anthropic.Anthropic(max_retries=0,timeout=timeout) as client:
            response=client.messages.create(model=model,max_tokens=limit,system=system,
                                            messages=[{'role':'user','content':user}])
        answer=''.join(block.text for block in response.content if block.type=='text')
        raw=met.plain(response.usage);complete=response.stop_reason=='end_turn'
        extra=dict(resolved_model=response.model,finish_reason=response.stop_reason,
                   request_id=getattr(response,'_request_id',None))
    elif provider=='azure':
        from openai import OpenAI
        root=os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')
        if root.endswith('/responses'):root=root[:-len('/responses')]
        if not root.endswith('/openai/v1'):root+='/openai/v1'
        with OpenAI(base_url=root+'/',api_key=os.environ['AZURE_OPENAI_API_KEY'],max_retries=0,timeout=timeout) as client:
            response=client.chat.completions.create(model=model,max_completion_tokens=limit,
                messages=[{'role':'system','content':system},{'role':'user','content':user}])
        choice=response.choices[0] if response.choices else None
        answer=choice.message.content if choice else '';raw=met.plain(response.usage)
        complete=bool(choice and choice.finish_reason=='stop')
        extra=dict(resolved_model=response.model,finish_reason=choice.finish_reason if choice else 'no_choices',
                   request_id=getattr(response,'_request_id',None))
    elif provider=='vertex':
        from google import genai
        from google.genai import types
        with genai.Client(vertexai=True,project=config['project'],location=config['location'],
                          http_options=types.HttpOptions(timeout=timeout*1000,retry_options=types.HttpRetryOptions(attempts=1))) as client:
            response=client.models.generate_content(model=model,contents=user,
                config=types.GenerateContentConfig(system_instruction=system,max_output_tokens=limit,response_mime_type='application/json'))
        answer=response.text or '';raw=met.plain(response.usage_metadata)
        finish=str(getattr(response.candidates[0],'finish_reason','no_candidates')).split('.')[-1] if response.candidates else 'no_candidates'
        complete=finish=='STOP'
        extra=dict(resolved_model=getattr(response,'model_version',None),finish_reason=finish,
                   request_id=getattr(response,'response_id',None))
    else:raise ValueError('Unsupported judge provider')
    usage=met.normalize_usage(provider,raw)
    usage.update(extra,usage_raw=raw,done=complete,done_reason='stop' if complete else extra['finish_reason'])
    usage.update(met.estimate_cost(provider,model,usage,config['prices'],config['pricing_date']))
    return answer,usage


def estimated_call_cost(system,user,config):
    # A disclosed planning scenario, not actual token usage or a guaranteed billing ceiling.
    assumed_input=len((system+user).encode('utf-8'))
    usage=dict(input_tokens=assumed_input,output_tokens=config['max_output_tokens'],
               cached_input_tokens=0,cache_creation_tokens=0)
    return metrics().estimate_cost(config['provider'],config['model'],usage,config['prices'],config['pricing_date'])

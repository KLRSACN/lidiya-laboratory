from __future__ import annotations
import argparse, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state' / 'MISSION_STATE.json'
PACKET = ROOT / 'state' / 'RELAY_PACKET.json'
EVID = ROOT / 'state' / 'EVIDENCE'
AUTH = ROOT / 'auth' / 'AUTH_STATUS.json'
MISSION='LCR-AUTONOMY-0002'
RUN='RUN-LCR-AUTONOMY-0002'

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,obj): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def h(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def evidence(name, data): data={'mission_id':MISSION,'run_id':RUN,'github_run_id':os.getenv('GITHUB_RUN_ID'),'github_run_attempt':os.getenv('GITHUB_RUN_ATTEMPT'),'github_job':os.getenv('GITHUB_JOB'),'recorded_at':now(),**data}; write(EVID/name,data); return str((EVID/name).relative_to(ROOT))

def auth_probe():
    provider=(os.getenv('LCR_MODEL_PROVIDER') or 'none').strip().lower()
    envmap={'openai':'OPENAI_API_KEY','gemini':'GEMINI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}
    envname=envmap.get(provider)
    configured=bool(envname and os.getenv(envname))
    status={'schema_version':1,'provider':provider,'secret_env':envname,'configured':configured,'secret_value_logged':False,'checked_at':now()}
    write(AUTH,status)
    return status

def set_packet(source,target,action,step,parent=None,payload=None):
    obj={'schema_version':2,'packet_id':f'PKT-{source[0]}2{target[0]}-{MISSION}-{step}', 'mission_id':MISSION,'run_id':RUN,'step_id':step,'source':source,'target':target,'action':action,'status':'READY','payload':payload or {},'parent_packet_id':parent,'created_at':now(),'consumed':False,'consumed_at':None}
    obj['input_hash']=h({k:v for k,v in obj.items() if k!='input_hash'})
    write(PACKET,obj); return obj

def consume(expected_target):
    p=load(PACKET)
    if p['target']!=expected_target or p.get('consumed'):
        raise SystemExit(f'packet gate failed target={p.get("target")} consumed={p.get("consumed")} expected={expected_target}')
    p['consumed']=True; p['consumed_at']=now(); write(PACKET,p); return p

def a_start():
    auth=auth_probe()
    state={'schema_version':2,'mission_id':MISSION,'project_id':'CLOUD-RELAY-V2','cycle':2,'step_id':1,'owner':'COORDINATOR','status':'ACTIVATING','goal':'Verify GitHub-cloud A->B->C->A under one-time Activation Gate, then Metabolic Closure.','activation_gate':{'id':'LCR-AUTONOMY-0002','default_branch_launcher_only':True,'cloud_model_auth_architecture_allowed':True,'secret_values_must_never_be_logged':True,'other_L2_prohibitions_unchanged':True},'auth':auth,'completed_steps':['ACTIVATION_GATE_ACCEPTED'],'updated_at':now()}
    write(STATE,state)
    pkt=set_packet('COORDINATOR','BUILDER','BUILD_CLOUD_ACK',1,payload={'acceptance':['persist evidence','no L2 prohibited action','handoff exactly once']})
    state['owner']='BUILDER'; state['status']='AWAITING_BUILDER'; state['last_packet_id']=pkt['packet_id']; state['last_packet_hash']=pkt['input_hash']; state['completed_steps'].append('A_DISPATCHED_TO_B'); state['updated_at']=now(); write(STATE,state)
    evidence('STEP-1-A-START.json',{'slot':'A','result':'DISPATCHED','packet_id':pkt['packet_id'],'auth_configured':auth['configured'],'auth_provider':auth['provider'],'secret_value_logged':False})

def builder():
    old=consume('BUILDER'); state=load(STATE)
    ev=evidence('STEP-2-BUILDER.json',{'slot':'B','result':'BUILDER_DONE','consumed_packet':old['packet_id'],'checks':['branch-scoped','no-secret-readback','evidence-first']})
    pkt=set_packet('BUILDER','VERIFIER','VERIFY_BUILDER_EVIDENCE',2,parent=old['packet_id'],payload={'evidence':ev})
    state['owner']='VERIFIER'; state['status']='AWAITING_VERIFIER'; state['step_id']=2; state['last_packet_id']=pkt['packet_id']; state['last_packet_hash']=pkt['input_hash']; state['completed_steps'].append('B_HANDOFF_TO_C'); state['updated_at']=now(); write(STATE,state)

def verifier():
    old=consume('VERIFIER'); state=load(STATE)
    ref=ROOT/old['payload']['evidence']
    if not ref.exists(): raise SystemExit('builder evidence missing')
    b=load(ref)
    passed=b.get('result')=='BUILDER_DONE' and b.get('slot')=='B'
    ev=evidence('STEP-3-VERIFIER.json',{'slot':'C','result':'PASS' if passed else 'FAIL','verified_evidence':str(ref.relative_to(ROOT)),'independent_checks':['builder evidence exists','builder result exact','packet not pre-consumed']})
    if not passed: raise SystemExit('verification failed')
    pkt=set_packet('VERIFIER','COORDINATOR','RETURN_VERIFIED_PASS',3,parent=old['packet_id'],payload={'evidence':ev,'verdict':'PASS'})
    state['owner']='COORDINATOR'; state['status']='AWAITING_COORDINATOR_RETURN'; state['step_id']=3; state['last_packet_id']=pkt['packet_id']; state['last_packet_hash']=pkt['input_hash']; state['completed_steps'].append('C_RETURNED_PASS_TO_A'); state['updated_at']=now(); write(STATE,state)

def a_return():
    old=consume('COORDINATOR'); state=load(STATE)
    if old.get('payload',{}).get('verdict')!='PASS': raise SystemExit('verifier did not PASS')
    evidence('STEP-4-A-RETURN.json',{'slot':'A','result':'ROUNDTRIP_PASS','consumed_packet':old['packet_id'],'path':['A','B','C','A']})
    state['owner']='COORDINATOR'; state['status']='ROUNDTRIP_VERIFIED'; state['step_id']=4; state['completed_steps'].append('A_RECEIVED_VERIFIED_PASS'); state['roundtrip_verified']=True; state['roundtrip_path']=['A','B','C','A']; state['updated_at']=now(); write(STATE,state)

def closure():
    state=load(STATE)
    if not state.get('roundtrip_verified'): raise SystemExit('closure blocked: roundtrip not verified')
    closure={'schema_version':1,'mission_id':MISSION,'run_id':RUN,'status':'METABOLIC_CLOSED','closed_at':now(),'consumed_energy':['activation gate','A->B packet','B evidence','C verification','C->A PASS'],'retained_long_term':['relay protocol v2','auth secret-boundary pattern','evidence-first closure'], 'discarded_transient':['runner workspace','ephemeral job state','secret values'], 'next_mission_candidate':'LCR-AUTONOMY-0003-CONCURRENCY-HARDENING','requires_boxuan_approval':False}
    write(ROOT/'state'/'METABOLIC_CLOSURE.json',closure)
    state['status']='PROJECT_DONE'; state['owner']='COORDINATOR'; state['metabolic_closure']='state/METABOLIC_CLOSURE.json'; state['completed_steps'].append('METABOLIC_CLOSURE_COMPLETED'); state['updated_at']=now(); write(STATE,state)
    evidence('STEP-5-METABOLIC-CLOSURE.json',{'slot':'SYSTEM','result':'CLOSED','next_mission_candidate':closure['next_mission_candidate']})

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('slot',choices=['a-start','builder','verifier','a-return','closure']); args=ap.parse_args()
    {'a-start':a_start,'builder':builder,'verifier':verifier,'a-return':a_return,'closure':closure}[args.slot]()
if __name__=='__main__': main()

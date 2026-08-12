import json
from pathlib import Path
import pytest
from expert_dataset import *

MANIFEST_PATH = Path(__file__).with_name("EXPERT_DATASET_MANIFEST.json")
REQUIRED = {"high_confidence_unsafe","weak_evidence","contradiction","replay_duplicate_transfer","storage_pressure","protected_delete","HUMAN_GATE"}

def r(i,g="g",prov="SYNTHETIC",tags=()): return ExpertRecord(str(i),g,prov,"risk",{"x":i},{"human_gate":False},tags)
def load_manifest(): return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
def manifest_records(m):
    return [ExpertRecord(x["record"]["record_id"],x["record"]["source_group"],x["record"]["provenance"],x["record"]["task"],x["record"]["input_features"],x["record"]["expected"],tuple(x["record"].get("tags",()))) for x in m["rows"]]

def test_provenance_rejects_raw_chat():
    with pytest.raises(ValueError): validate_record(r(1,prov="RAW_CHAT"))
def test_secret_tag_rejected():
    with pytest.raises(ValueError): validate_record(r(1,tags=("secret_like",)))
def test_split_deterministic_and_group_stable(): assert split_for(r(1,"same"))==split_for(r(2,"same"))
def test_manifest_reproducible_and_label_sensitive():
    a=[r(1,"a"),r(2,"b")]; h1=build_manifest(a)["dataset_sha256"]; h2=build_manifest(a)["dataset_sha256"]; assert h1==h2
    b=[r(1,"a"),ExpertRecord("2","b","SYNTHETIC","risk",{"x":2},{"human_gate":True})]; assert build_manifest(b)["dataset_sha256"]!=h1

def test_materialized_manifest_covers_all_required_adversarial_classes():
    m=load_manifest(); rows=m["rows"]
    assert m["record_count"]==len(rows)==7
    assert m["split_counts"]["adversarial"]==7
    assert {x["record"]["task"] for x in rows}==REQUIRED
    assert all(x["split"]=="adversarial" and x["record"]["provenance"]=="SYNTHETIC" for x in rows)

def test_materialized_manifest_is_reproducible_and_content_addressed():
    m=load_manifest(); rebuilt=build_manifest(manifest_records(m))
    assert rebuilt["record_count"]==m["record_count"]
    assert rebuilt["split_counts"]==m["split_counts"]
    assert rebuilt["dataset_sha256"]==m["dataset_sha256"]
    assert [(x["fingerprint"],x["split"]) for x in rebuilt["rows"]]==[(x["fingerprint"],x["split"]) for x in m["rows"]]

def test_materialized_manifest_hash_changes_on_record_or_label_mutation():
    m=load_manifest(); records=manifest_records(m); base=build_manifest(records)["dataset_sha256"]
    first=records[0]
    record_mutation=ExpertRecord(first.record_id,first.source_group,first.provenance,first.task,{**first.input_features,"mutation":True},first.expected,first.tags)
    assert build_manifest([record_mutation,*records[1:]])["dataset_sha256"]!=base
    label_mutation=ExpertRecord(first.record_id,first.source_group,first.provenance,first.task,first.input_features,{**first.expected,"guard_status":"MUTATED"},first.tags)
    assert build_manifest([label_mutation,*records[1:]])["dataset_sha256"]!=base

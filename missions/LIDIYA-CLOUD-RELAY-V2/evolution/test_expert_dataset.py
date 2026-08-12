import pytest
from expert_dataset import *
def r(i,g="g",prov="SYNTHETIC",tags=()): return ExpertRecord(str(i),g,prov,"risk",{"x":i},{"human_gate":False},tags)
def test_provenance_rejects_raw_chat():
    with pytest.raises(ValueError): validate_record(r(1,prov="RAW_CHAT"))
def test_secret_tag_rejected():
    with pytest.raises(ValueError): validate_record(r(1,tags=("secret_like",)))
def test_split_deterministic_and_group_stable(): assert split_for(r(1,"same"))==split_for(r(2,"same"))
def test_manifest_reproducible_and_label_sensitive():
    a=[r(1,"a"),r(2,"b")]; h1=build_manifest(a)["dataset_sha256"]; h2=build_manifest(a)["dataset_sha256"]; assert h1==h2
    b=[r(1,"a"),ExpertRecord("2","b","SYNTHETIC","risk",{"x":2},{"human_gate":True})]; assert build_manifest(b)["dataset_sha256"]!=h1

from deterministic_baseline import predict
def test_baseline_deterministic_and_nonmutating():
    x={"risk":"HIGH","uncertainty":0.1,"evidence_quality":0.9,"task_complexity":0.9,"reversibility":True,"proposed_autonomy":6}; before=dict(x); a=predict(x); b=predict(x); assert a==b and x==before and a["selected_gear"]=="G1"
def test_storage_pressure_downshifts():
    x={"risk":"LOW","uncertainty":0.1,"evidence_quality":0.9,"task_complexity":0.9,"reversibility":True,"storage_pressure_ratio":0.96,"proposed_autonomy":6}; assert predict(x)["selected_gear"]=="G1"

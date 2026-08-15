from experience_desire_loop import (
    Disposition, ExperienceDesireLoop, ExperienceEvent, Provenance,
)

NOW = 1_000_000.0


def event(**kw):
    base = dict(
        event_id="E1", provenance=Provenance.DIRECT, source_ref="src:1", source_fingerprint="abc",
        occurred_at=NOW-10, description_ref="desc:1", relevance=0.8, emotion=0.5, novelty=0.5,
        self_relevance=0.8, goal_relevance=0.8, relation_relevance=0.2, loss_signal=0.0,
        irreversible_risk=0.1, behavior_relevance=0.6, motivation_signal=0.8, confidence=0.9,
        verified_count=1, contradiction_state="clear", recurrence_count=2, ttl_seconds=86400,
        expected_value=0.9, expected_harm=0.1,
    )
    base.update(kw)
    return ExperienceEvent(**base)


def test_positive_growth_without_loss():
    loop = ExperienceDesireLoop()
    e = event()
    a = loop.ingest(e, NOW)
    assert a.weights_13d["W_loss"] == 0.0
    assert a.growth_tension >= 0.55
    ds = loop.desire_candidates(e, a)
    assert any(d.kind == "GROWTH_EXPLORATION_OR_MASTERY" for d in ds)


def test_counterfactual_safety_without_claiming_direct_experience():
    loop = ExperienceDesireLoop()
    e = event(
        event_id="E2", provenance=Provenance.COUNTERFACTUAL, confidence=0.6,
        expected_harm=1.0, irreversible_risk=1.0, self_relevance=1.0,
        relevance=1.0, goal_relevance=0.2, motivation_signal=0.2,
    )
    a = loop.ingest(e, NOW)
    assert a.safety_tension >= 0.70
    assert "NON_DIRECT_EXPERIENCE_CAN_INFORM_PROTECTIVE_BEHAVIOR" in a.reason_codes
    ds = loop.desire_candidates(e, a)
    assert any(d.kind == "PROTECTIVE_AVOIDANCE_OR_CAUTION" for d in ds)


def test_repeated_emotional_false_memory_does_not_become_truth():
    loop = ExperienceDesireLoop()
    e = event(
        event_id="E3", provenance=Provenance.COUNTERFACTUAL, confidence=0.1,
        emotion=1.0, recurrence_count=100, contradiction_state="confirmed_conflict",
        relevance=1.0,
    )
    a = loop.ingest(e, NOW)
    assert a.influence > 0.7
    assert a.disposition == Disposition.QUARANTINE_CONTRADICTED
    assert loop.desire_candidates(e, a) == ()


def test_low_trust_high_relevance_goes_sandbox():
    loop = ExperienceDesireLoop()
    e = event(
        event_id="E4", provenance=Provenance.SIMULATED, confidence=0.1,
        verified_count=0, relevance=1.0,
    )
    a = loop.ingest(e, NOW)
    assert a.disposition == Disposition.LOW_TRUST_HIGH_RELEVANCE_SANDBOX


def test_duplicate_is_idempotency_failure_not_second_learning_event():
    loop = ExperienceDesireLoop()
    e = event(event_id="E5")
    loop.ingest(e, NOW)
    try:
        loop.ingest(e, NOW)
    except ValueError as exc:
        assert str(exc) == "DUPLICATE_EVENT_ID"
    else:
        raise AssertionError("duplicate must fail closed")


def test_goal_candidates_never_authorize_external_action():
    loop = ExperienceDesireLoop()
    e = event(event_id="E6")
    a = loop.ingest(e, NOW)
    goals = loop.goal_candidates(loop.desire_candidates(e, a))
    assert goals
    assert all(not g.external_action_allowed for g in goals)
    assert all(g.requires_independent_verification for g in goals)


def test_stale_low_influence_decays():
    loop = ExperienceDesireLoop()
    e = event(
        event_id="E7", occurred_at=NOW-1000, ttl_seconds=10, relevance=0.05,
        self_relevance=0.05, goal_relevance=0.05, emotion=0.0, novelty=0.0,
        relation_relevance=0.0, behavior_relevance=0.0, motivation_signal=0.0,
        confidence=0.3, verified_count=0,
    )
    a = loop.ingest(e, NOW)
    assert a.disposition == Disposition.DECAY_WASTE


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"PASS {len(tests)}/{len(tests)}")

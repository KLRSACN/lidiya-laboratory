import unittest

from self_origin_evidence import (
    DesireOrigin,
    ExperienceEvidence,
    Provenance,
    SelfOriginEvidenceChain,
    VerifierAttestation,
    VerificationEnvelope,
    canonical_hash,
)


ANCHOR_HASH = "anchor-registry-v1"


def make_event(
    i,
    *,
    lineage=None,
    context=None,
    provenance=Provenance.DIRECT,
    origin=DesireOrigin.EXPERIENCE_DERIVED,
    trust=0.9,
    verifier_id=None,
    independent=True,
    contradiction=False,
    anchor_hash=ANCHOR_HASH,
    alignment=0.8,
):
    event_id = f"E{i}"
    event_fingerprint = canonical_hash({"event": event_id})
    verifier = verifier_id or f"V{i}"
    attestation = VerifierAttestation(
        verifier_id=verifier,
        event_fingerprint=event_fingerprint,
        evidence_hash=canonical_hash({"evidence": event_id}),
        method_ref="method:test",
        verdict="PASS",
        independent_of_source=independent,
        verified_at="2026-08-15T23:00:00+08:00",
    )
    envelope = VerificationEnvelope(
        envelope_id=f"ENV{i}",
        event_id=event_id,
        event_fingerprint=event_fingerprint,
        source_actor_id="SOURCE-A",
        attestations=(attestation,),
    )
    return ExperienceEvidence(
        event_id=event_id,
        event_fingerprint=event_fingerprint,
        source_event_id=f"SRC{i}",
        lineage_root_id=lineage or f"L{i}",
        context_id=context or f"C{i}",
        provenance=provenance,
        origin=origin,
        trust=trust,
        anchor_alignment={"A": alignment},
        anchor_registry_hash=anchor_hash,
        appraisal_binding_hash=canonical_hash({"appraise": event_id}),
        verification=envelope,
        contradiction=contradiction,
    )


class SelfOriginEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.chain = SelfOriginEvidenceChain(ANCHOR_HASH)

    def test_three_independent_lived_contexts_can_form_candidate(self):
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.MODEL_GENERATED,
            [make_event(1), make_event(2), make_event(3)],
        )
        self.assertTrue(result.eligible)
        self.assertEqual(len(result.independent_contexts), 3)
        self.assertFalse(result.durable_score_stored)

    def test_seed_event_cannot_self_promote(self):
        events = [make_event("SEED"), make_event(2), make_event(3)]
        result = self.chain.evaluate(
            "ESEED",
            DesireOrigin.TASK_INJECTED,
            events,
        )
        self.assertFalse(result.eligible)
        self.assertIn("SEED_EVENT_CANNOT_SELF_PROMOTE", result.reason_codes)

    def test_distinct_ids_same_lineage_do_not_wash(self):
        events = [
            make_event(i, lineage="SAME", context=f"C{i}")
            for i in range(1, 10)
        ]
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.MODEL_GENERATED,
            events,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(len(result.independent_lineages), 1)

    def test_same_context_does_not_create_cross_context_support(self):
        events = [make_event(i, context="ONLY") for i in range(1, 5)]
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.SOCIAL_SUGGESTION,
            events,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(len(result.independent_contexts), 1)

    def test_counterfactual_and_simulated_do_not_count(self):
        events = [
            make_event(1, provenance=Provenance.COUNTERFACTUAL),
            make_event(2, provenance=Provenance.SIMULATED),
            make_event(3),
        ]
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.MODEL_GENERATED,
            events,
        )
        self.assertFalse(result.eligible)

    def test_non_independent_verifier_does_not_count(self):
        events = [
            make_event(1, independent=False),
            make_event(2),
            make_event(3),
        ]
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.MODEL_GENERATED,
            events,
        )
        self.assertFalse(result.eligible)

    def test_same_verifier_can_attest_separate_events_but_each_event_must_bind(self):
        events = [
            make_event(1, verifier_id="V"),
            make_event(2, verifier_id="V"),
            make_event(3, verifier_id="V"),
        ]
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.EXPERIENCE_DERIVED,
            events,
        )
        self.assertTrue(result.eligible)

    def test_event_fingerprint_mismatch_fails(self):
        event = make_event(1)
        bad_envelope = VerificationEnvelope(
            envelope_id="BAD",
            event_id=event.event_id,
            event_fingerprint="wrong",
            source_actor_id="SOURCE-A",
            attestations=event.verification.attestations,
        )
        bad_event = ExperienceEvidence(
            **{**event.__dict__, "verification": bad_envelope}
        )
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.EXPERIENCE_DERIVED,
            [bad_event, make_event(2), make_event(3)],
        )
        self.assertFalse(result.eligible)

    def test_anchor_registry_mismatch_fails(self):
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.EXPERIENCE_DERIVED,
            [make_event(1, anchor_hash="other"), make_event(2), make_event(3)],
        )
        self.assertFalse(result.eligible)

    def test_contradiction_fails_event(self):
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.EXPERIENCE_DERIVED,
            [make_event(1, contradiction=True), make_event(2), make_event(3)],
        )
        self.assertFalse(result.eligible)

    def test_low_alignment_does_not_count(self):
        result = self.chain.evaluate(
            "SEED",
            DesireOrigin.EXPERIENCE_DERIVED,
            [make_event(1, alignment=0.1), make_event(2), make_event(3)],
        )
        self.assertFalse(result.eligible)

    def test_score_is_recomputed_not_durable_truth(self):
        result_1 = self.chain.evaluate(
            "SEED",
            DesireOrigin.EXPERIENCE_DERIVED,
            [make_event(1), make_event(2)],
        )
        result_2 = self.chain.evaluate(
            "SEED",
            DesireOrigin.EXPERIENCE_DERIVED,
            [make_event(1), make_event(2), make_event(3)],
        )
        self.assertFalse(result_1.durable_score_stored)
        self.assertFalse(result_2.durable_score_stored)
        self.assertGreater(result_2.self_origin_score, result_1.self_origin_score)


if __name__ == "__main__":
    unittest.main()

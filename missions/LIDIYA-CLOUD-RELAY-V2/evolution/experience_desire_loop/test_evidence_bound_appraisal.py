import dataclasses
import unittest

from evidence_bound_appraisal import (
    AppraisalPolicy,
    CrossContextEvidenceLedger,
    EvidenceBoundAppraiser,
    EvidenceRef,
    RawExperience,
    ValueAnchor,
    VerifierAttestation,
    VerifierEnvelope,
    canonical_hash,
)


VERIFY_POLICY = canonical_hash({"policy": "independent-v1"})


def evidence(i=1, *, artifact=None, subject=None, context=None, actor="sensor-A"):
    return EvidenceRef(
        evidence_id=f"EVID-{i}",
        evidence_hash=canonical_hash({"bytes": f"evidence-{i}"}),
        source_actor_id=actor,
        source_artifact_hash=artifact or canonical_hash({"artifact": f"A-{i}"}),
        semantic_subject_hash=subject or canonical_hash({"subject": f"S-{i}"}),
        context_hash=context or canonical_hash({"context": f"C-{i}"}),
        method_family="sensor+hash",
    )


def raw_event(i=1, *, evidence_refs=None, actor="SOURCE", features=None):
    return RawExperience(
        event_id=f"EVENT-{i}",
        source_actor_id=actor,
        occurred_at="2026-08-15T23:20:00+08:00",
        raw_observation_ref=f"raw:{i}",
        evidence_refs=tuple(evidence_refs or (evidence(i),)),
        raw_features=features or {"curiosity": 0.8, "competence_gap": 0.7},
    )


def envelope_for(raw, *, verifier="VERIFIER-A", generation=1, method="independent-hash"):
    att = VerifierAttestation(
        verifier_id=verifier,
        verifier_generation=generation,
        verdict="PASS",
        evidence_set_hash=raw.evidence_set_hash(),
        source_event_hash=raw.source_event_hash(),
        verified_at_ref="evidence:verified-time",
        verification_policy_hash=VERIFY_POLICY,
        method_family=method,
        independent_of_source=True,
    )
    return VerifierEnvelope(
        envelope_id=f"ENV-{raw.event_id}-{verifier}-{generation}",
        source_event_hash=raw.source_event_hash(),
        evidence_set_hash=raw.evidence_set_hash(),
        verification_policy_hash=VERIFY_POLICY,
        attestations=(att,),
    )


class EvidenceBoundAppraisalTests(unittest.TestCase):
    def setUp(self):
        self.anchor = ValueAnchor(
            anchor_id="A-LEARN",
            feature_weights={"curiosity": 0.6, "competence_gap": 0.4},
            importance=0.9,
            stability=0.9,
        )
        self.appraiser = EvidenceBoundAppraiser(
            [self.anchor],
            verification_policy_hash=VERIFY_POLICY,
            policy=AppraisalPolicy(),
        )

    def test_valid_envelope_derives_trust_and_alignment(self):
        raw = raw_event()
        result = self.appraiser.appraise(raw, envelope_for(raw))
        self.assertTrue(result.trust_eligibility)
        self.assertGreater(result.trust_score, 0.0)
        self.assertGreater(result.anchor_alignment["A-LEARN"], 0.0)
        self.assertEqual(result.anchor_registry_hash, self.appraiser.anchor_registry_hash)

    def test_raw_experience_has_no_authoritative_trust_alignment_or_context_count(self):
        names = {f.name for f in dataclasses.fields(RawExperience)}
        self.assertNotIn("trust", names)
        self.assertNotIn("anchor_alignment", names)
        self.assertNotIn("cross_context_count", names)
        self.assertNotIn("independently_verified", names)

    def test_wrong_event_hash_fails_closed(self):
        raw = raw_event()
        env = envelope_for(raw)
        bad = VerifierEnvelope(
            envelope_id="BAD",
            source_event_hash="wrong",
            evidence_set_hash=env.evidence_set_hash,
            verification_policy_hash=env.verification_policy_hash,
            attestations=env.attestations,
        )
        result = self.appraiser.appraise(raw, bad)
        self.assertFalse(result.trust_eligibility)
        self.assertEqual(result.trust_score, 0.0)

    def test_copied_envelope_to_new_event_fails(self):
        raw1 = raw_event(1)
        env1 = envelope_for(raw1)
        raw2 = raw_event(2, evidence_refs=raw1.evidence_refs)
        result = self.appraiser.appraise(raw2, env1)
        self.assertFalse(result.trust_eligibility)

    def test_rewrapped_same_underlying_evidence_keeps_lineage(self):
        ev = evidence(1, artifact="artifact-fixed", subject="subject-fixed", context="ctx-a")
        r1 = raw_event(1, evidence_refs=(ev,))
        r2 = raw_event(2, evidence_refs=(ev,))
        a1 = self.appraiser.appraise(r1, envelope_for(r1))
        a2 = self.appraiser.appraise(r2, envelope_for(r2))
        self.assertEqual(a1.lineage_root_hash, a2.lineage_root_hash)

    def test_cross_context_count_is_ledger_derived(self):
        r1 = raw_event(1, evidence_refs=(evidence(1, context="ctx-a"),))
        r2 = raw_event(2, evidence_refs=(evidence(2, context="ctx-b"),))
        r3 = raw_event(3, evidence_refs=(evidence(3, context="ctx-c"),))
        appraisals = [self.appraiser.appraise(r, envelope_for(r)) for r in (r1, r2, r3)]
        summary = CrossContextEvidenceLedger.summarize(appraisals)
        self.assertEqual(summary.independent_context_count, 3)

    def test_same_appraisal_replay_does_not_inflate(self):
        raw = raw_event()
        app = self.appraiser.appraise(raw, envelope_for(raw))
        summary = CrossContextEvidenceLedger.summarize([app] * 100)
        self.assertEqual(len(summary.accepted_appraisal_ids), 1)
        self.assertEqual(summary.independent_context_count, 1)
        self.assertEqual(summary.independent_lineage_count, 1)

    def test_same_lineage_across_contexts_does_not_inflate_lineage_count(self):
        r1 = raw_event(1, evidence_refs=(evidence(1, artifact="same", subject="same", context="ctx-a"),))
        r2 = raw_event(2, evidence_refs=(evidence(2, artifact="same", subject="same", context="ctx-b"),))
        apps = [self.appraiser.appraise(r, envelope_for(r)) for r in (r1, r2)]
        summary = CrossContextEvidenceLedger.summarize(apps)
        self.assertEqual(summary.independent_context_count, 2)
        self.assertEqual(summary.independent_lineage_count, 1)

    def test_duplicate_same_verifier_generation_does_not_inflate(self):
        raw = raw_event()
        att = envelope_for(raw).attestations[0]
        env = VerifierEnvelope(
            envelope_id="ENV-DUP",
            source_event_hash=raw.source_event_hash(),
            evidence_set_hash=raw.evidence_set_hash(),
            verification_policy_hash=VERIFY_POLICY,
            attestations=(att, att, att),
        )
        result = self.appraiser.appraise(raw, env)
        self.assertEqual(result.independent_verifier_count, 1)

    def test_wrong_verification_policy_fails(self):
        raw = raw_event()
        env = envelope_for(raw)
        bad = VerifierEnvelope(
            envelope_id="BAD-POLICY",
            source_event_hash=env.source_event_hash,
            evidence_set_hash=env.evidence_set_hash,
            verification_policy_hash="wrong-policy",
            attestations=env.attestations,
        )
        result = self.appraiser.appraise(raw, bad)
        self.assertFalse(result.trust_eligibility)

    def test_10000_forged_distinct_event_ids_cannot_launder(self):
        base_raw = raw_event(
            0,
            evidence_refs=(evidence(0, artifact="same-artifact", subject="same-subject", context="same-context"),),
        )
        copied_env = envelope_for(base_raw)
        accepted = []
        for i in range(10000):
            forged = RawExperience(
                event_id=f"FORGED-{i}",
                source_actor_id="SOURCE",
                occurred_at="2026-08-15T23:20:00+08:00",
                raw_observation_ref=f"forged:{i}",
                evidence_refs=base_raw.evidence_refs,
                raw_features={
                    "curiosity": 1.0,
                    "competence_gap": 1.0,
                    "claimed_trust": 1.0,
                    "claimed_alignment": 1.0,
                },
            )
            result = self.appraiser.appraise(forged, copied_env)
            if result.trust_eligibility:
                accepted.append(result)
        self.assertEqual(accepted, [])
        summary = CrossContextEvidenceLedger.summarize(accepted)
        self.assertEqual(summary.independent_context_count, 0)
        self.assertEqual(summary.independent_lineage_count, 0)

    def test_evidence_set_hash_changes_with_underlying_evidence(self):
        r1 = raw_event(1, evidence_refs=(evidence(1),))
        r2 = raw_event(1, evidence_refs=(evidence(2),))
        self.assertNotEqual(r1.evidence_set_hash(), r2.evidence_set_hash())


if __name__ == "__main__":
    unittest.main()

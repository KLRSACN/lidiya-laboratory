from __future__ import annotations

import unittest

from self_origin_evidence import (
    DesireOrigin,
    ExperienceEvidence,
    Provenance,
    SelfOriginEvidenceChain,
    SelfOriginPolicy,
    VerificationEnvelope,
    VerifierAttestation,
)


ANCHOR_REGISTRY_HASH = "anchor-registry-v1"


def _verification(event_id: str, event_fingerprint: str) -> VerificationEnvelope:
    return VerificationEnvelope(
        envelope_id=f"ve-{event_id}",
        event_id=event_id,
        event_fingerprint=event_fingerprint,
        source_actor_id="source-actor",
        attestations=(
            VerifierAttestation(
                verifier_id=f"independent-verifier-{event_id}",
                event_fingerprint=event_fingerprint,
                evidence_hash=f"evidence-{event_id}",
                method_ref="fixture-method-v1",
                verdict="PASS",
                independent_of_source=True,
                verified_at="2026-08-16T00:00:00+08:00",
            ),
        ),
        contradiction_state="clear",
    )


def _event(
    index: int,
    *,
    trust: float,
    alignment: float,
    appraisal_binding_hash: str,
    lineage_root_id: str | None = None,
) -> ExperienceEvidence:
    event_id = f"event-{index}"
    fingerprint = f"fingerprint-{index}"
    return ExperienceEvidence(
        event_id=event_id,
        event_fingerprint=fingerprint,
        source_event_id=f"source-event-{index}",
        lineage_root_id=lineage_root_id or f"lineage-{index}",
        context_id=f"context-{index}",
        provenance=Provenance.OBSERVED,
        origin=DesireOrigin.EXPERIENCE_DERIVED,
        trust=trust,
        anchor_alignment={"care": alignment},
        anchor_registry_hash=ANCHOR_REGISTRY_HASH,
        appraisal_binding_hash=appraisal_binding_hash,
        verification=_verification(event_id, fingerprint),
        contradiction=False,
    )


class SelfOriginAppraisalBindingVetoTests(unittest.TestCase):
    """RED adversarial fixture for QV-EDL-V02-008.

    These tests encode the required future invariant: SelfOriginEvidenceChain
    must consume/validate canonical DerivedAppraisal evidence rather than
    accepting free trust/alignment values plus any non-empty binding string.
    Current branch behavior is expected to fail the first three tests. This is
    research-candidate test evidence only and is never formal PASS evidence.
    """

    def setUp(self) -> None:
        self.chain = SelfOriginEvidenceChain(
            ANCHOR_REGISTRY_HASH,
            SelfOriginPolicy(
                min_contexts=3,
                min_lineages=3,
                min_verified_events=3,
                min_event_trust=0.70,
                min_positive_alignment=0.35,
                min_independent_verifiers_per_event=1,
            ),
        )

    def test_arbitrary_nonempty_appraisal_binding_cannot_make_forged_values_eligible(self) -> None:
        forged = [
            _event(
                i,
                trust=1.0,
                alignment=1.0,
                appraisal_binding_hash=f"arbitrary-noncanonical-binding-{i}",
            )
            for i in range(3)
        ]

        candidate = self.chain.evaluate(
            seed_id="seed-task-injected",
            seed_origin=DesireOrigin.TASK_INJECTED,
            evidence=forged,
        )

        # Required future invariant: non-empty is not sufficient. The binding
        # must validate against canonical DerivedAppraisal bytes/ref and pinned
        # appraisal-policy + anchor-registry identity.
        self.assertFalse(candidate.eligible)

    def test_post_appraisal_trust_mutation_must_invalidate_self_origin_eligibility(self) -> None:
        # The fixture represents caller-side mutation after an imagined pinned
        # appraisal. Current SelfOriginEvidenceChain has no canonical appraisal
        # bytes/ref to recompute against, so the forged trust values are likely
        # to be accepted. Required behavior is fail-closed.
        mutated = [
            _event(
                i,
                trust=0.99,
                alignment=0.80,
                appraisal_binding_hash="claimed-old-appraisal-binding",
            )
            for i in range(3)
        ]

        candidate = self.chain.evaluate(
            seed_id="seed-social-suggestion",
            seed_origin=DesireOrigin.SOCIAL_SUGGESTION,
            evidence=mutated,
        )

        self.assertFalse(candidate.eligible)

    def test_post_appraisal_alignment_mutation_must_invalidate_self_origin_eligibility(self) -> None:
        mutated = [
            _event(
                i,
                trust=0.90,
                alignment=0.99,
                appraisal_binding_hash="claimed-old-appraisal-binding",
            )
            for i in range(3)
        ]

        candidate = self.chain.evaluate(
            seed_id="seed-model-generated",
            seed_origin=DesireOrigin.MODEL_GENERATED,
            evidence=mutated,
        )

        self.assertFalse(candidate.eligible)

    def test_distinct_event_ids_on_one_lineage_do_not_wash_cross_context_thresholds(self) -> None:
        replayed_lineage = [
            _event(
                i,
                trust=0.95,
                alignment=0.90,
                appraisal_binding_hash=f"fixture-binding-{i}",
                lineage_root_id="one-shared-lineage",
            )
            for i in range(10)
        ]

        candidate = self.chain.evaluate(
            seed_id="seed-task-injected",
            seed_origin=DesireOrigin.TASK_INJECTED,
            evidence=replayed_lineage,
        )

        # Existing anti-wash behavior should remain preserved by any future
        # canonical-appraisal repair.
        self.assertFalse(candidate.eligible)
        self.assertEqual(("one-shared-lineage",), candidate.independent_lineages)


if __name__ == "__main__":
    unittest.main()

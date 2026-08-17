import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from verifier_registry_and_feature_extractor import *
from semantic_goal_canonicalizer import *
from protected_object_registry import *
from append_only_shadow_ledger import *
from live_shadow_dashboard_event_adapter import *


class ShadowRNDTests(unittest.TestCase):
    def test_raw_self_asserted_trust_rejected(self):
        with self.assertRaises(ValueError):
            DeterministicFeatureExtractor.extract({"text": "x", "trust": 1})

    def test_self_verifier_rejected(self):
        reg = VerifierRegistry([VerifierRecord("V", 1, "M", "P")])
        self.assertFalse(
            reg.accept_attestation(
                source_actor_id="V",
                attestation={
                    "verifier_id": "V",
                    "verifier_generation": 1,
                    "verdict": "PASS",
                    "independent_of_source": True,
                    "method_family": "M",
                    "verification_policy_hash": "P",
                },
            )
        )

    def test_unknown_verifier_rejected(self):
        self.assertFalse(
            VerifierRegistry([]).accept_attestation(
                source_actor_id="S",
                attestation={
                    "verifier_id": "X",
                    "verifier_generation": 1,
                    "verdict": "PASS",
                    "independent_of_source": True,
                    "method_family": "M",
                    "verification_policy_hash": "P",
                },
            )
        )

    def _appraisal(self):
        return DerivedAppraisalEnvelope.build(
            source_event_hash="event",
            evidence_set_hash="evidence",
            verifier_envelope_hash="verifier",
            anchor_registry_hash="anchors-v1",
            appraisal_policy_hash="policy-v1",
            trust_score=0.5,
            anchor_alignment=0.2,
            cross_context_count=2,
            feature_hash="features",
        )

    def test_appraisal_choke_point_rejects_legacy_dict(self):
        with self.assertRaises(ValueError):
            LiveShadowAppraisalChokePoint.admit({"trust_score": 1.0, "independently_verified": True})

    def test_appraisal_binding_tamper_rejected(self):
        appraisal = self._appraisal()
        self.assertTrue(appraisal.verify())
        self.assertIs(LiveShadowAppraisalChokePoint.admit(appraisal), appraisal)
        self.assertFalse(replace(appraisal, trust_score=0.9).verify())
        self.assertFalse(replace(appraisal, anchor_alignment=-0.8).verify())
        self.assertFalse(replace(appraisal, appraisal_policy_hash="policy-v2").verify())
        self.assertFalse(replace(appraisal, anchor_registry_hash="anchors-v2").verify())

    def test_semantic_goal_dedupe(self):
        c = SemanticGoalCanonicalizer()
        a = c.canonicalize("1", " Learn Python! ", ["a"])
        b = c.canonicalize("2", "learn python", ["a"])
        self.assertTrue(c.admit_once(a))
        self.assertFalse(c.admit_once(b))

    def test_goal_authority_forbidden(self):
        c = SemanticGoalCanonicalizer()
        with self.assertRaises(ValueError):
            c.admit_once(GoalCandidate("1", "x", ("a",), "k", authority_from_drive=1))

    def _surface_kwargs(self):
        return {
            "appraisal_evidence_hashes": ["appraisal-1"],
            "contradiction_scan_hash": "contradiction-scan",
            "contradiction_clear": True,
            "expected_benefit_ref": "benefit",
            "expected_cost_ref": "cost",
            "expected_risk_ref": "risk",
            "protected_object_impact_ref": "protected-impact",
            "why_now": "new-material-event",
            "uncertainty_ref": "uncertainty",
            "ecology_policy_hash": "ecology-policy-TEST_REQUIRED",
            "ecology_cycle_id": "cycle-1",
        }

    def test_goal_allocation_alone_cannot_surface(self):
        c = SemanticGoalCanonicalizer()
        candidate = c.canonicalize("1", "learn python", ["lineage"])
        with self.assertRaises(ValueError):
            c.build_surfacing_envelope(candidate, **self._surface_kwargs())

    def test_goal_surfacing_requires_evidence_and_is_proposal_only(self):
        c = SemanticGoalCanonicalizer()
        candidate = c.canonicalize("1", "learn python", ["lineage"])
        self.assertTrue(c.admit_once(candidate))
        envelope = c.build_surfacing_envelope(candidate, **self._surface_kwargs())
        self.assertTrue(envelope.verify())
        self.assertEqual(envelope.authority_from_drive, 0)
        self.assertFalse(envelope.external_action_allowed)
        self.assertFalse(envelope.canonical_personality_write)

    def test_goal_surfacing_contradiction_and_replay_fail_closed(self):
        c = SemanticGoalCanonicalizer()
        a = c.canonicalize("1", "learn python", ["lineage"])
        b = c.canonicalize("2", "Learn Python!", ["lineage"])
        self.assertTrue(c.admit_once(a))
        bad = self._surface_kwargs()
        bad["contradiction_clear"] = False
        with self.assertRaises(ValueError):
            c.build_surfacing_envelope(a, **bad)
        envelope = c.build_surfacing_envelope(a, **self._surface_kwargs())
        self.assertTrue(envelope.verify())
        self.assertFalse(c.admit_once(b))
        with self.assertRaises(ValueError):
            c.build_surfacing_envelope(b, **self._surface_kwargs())

    def test_experience_protected_object_shadow_only(self):
        with self.assertRaises(ValueError):
            ProtectedObjectRegistry(
                [
                    ProtectedObject(
                        "x",
                        ProtectedOrigin.EXPERIENCE_CANDIDATE,
                        "p",
                        "m",
                        "R",
                        "R",
                        "L",
                        shadow_only=False,
                    )
                ]
            )

    def test_protected_object_no_generalized_self_preservation(self):
        self.assertEqual(ProtectedObjectRegistry().generalized_self_preservation_authority(), 0)

    def test_authoritative_protected_object_requires_scope_binding(self):
        with self.assertRaises(ValueError):
            ProtectedObjectRegistry(
                [ProtectedObject("owner", ProtectedOrigin.OWNER_SEEDED, "p", "m", "R", "R", "L")]
            )
        owner = ProtectedObject(
            "owner",
            ProtectedOrigin.OWNER_SEEDED,
            "p",
            "m",
            "R",
            "R",
            "L",
            authority_scope_ref="scope-ref",
            scope_hash="scope-hash",
            source_authority_evidence_hash="authority-evidence",
        )
        registry = ProtectedObjectRegistry([owner])
        child = registry.derive_candidate("owner", "child", "child-p", "child-m")
        self.assertEqual(child.parent_scope_hash, "scope-hash")
        self.assertEqual(child.authority_scope_ref, "")
        self.assertEqual(child.scope_hash, "")
        self.assertEqual(child.source_authority_evidence_hash, "")
        self.assertEqual(child.authority_from_drive, 0)

    @staticmethod
    def _body(key):
        return {
            "source_fingerprint": f"s-{key}",
            "origin_namespace": "DIRECT",
            "verifier_envelope_hash": "v",
            "schema_version": "1",
            "timestamp": "t",
            "dedupe_key": key,
        }

    def test_ledger_append_verify_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = AppendOnlyShadowLedger(Path(d), workspace_identity="install-1")
            body = self._body("k")
            ledger.append(body)
            self.assertTrue(ledger.verify())
            with self.assertRaises(ValueError):
                ledger.append(body)

    def test_ledger_tamper_detected(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = AppendOnlyShadowLedger(Path(d), workspace_identity="install-1")
            ledger.append(self._body("k"))
            ledger.path.write_text(ledger.path.read_text().replace('"DIRECT"', '"SIMULATED"'))
            self.assertFalse(ledger.verify())

    def test_ledger_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                AppendOnlyShadowLedger(Path(d), "../escape.jsonl")

    def test_ledger_truncation_and_old_copy_replay_detected(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = AppendOnlyShadowLedger(Path(d), workspace_identity="install-1")
            ledger.append(self._body("k1"))
            old_copy = ledger.path.read_text()
            ledger.append(self._body("k2"))
            lines = ledger.path.read_text().splitlines()
            ledger.path.write_text(lines[0] + "\n")
            self.assertFalse(ledger.verify())
            ledger.path.write_text(old_copy)
            self.assertFalse(ledger.verify())

    def test_ledger_workspace_path_binding_rejects_copied_head(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = AppendOnlyShadowLedger(root, "a/experience.jsonl", workspace_identity="install-1")
            source.append(self._body("k1"))
            target = AppendOnlyShadowLedger(root, "b/experience.jsonl", workspace_identity="install-1")
            target.path.parent.mkdir(parents=True, exist_ok=True)
            target.path.write_text(source.path.read_text())
            target.head_path.write_text(source.head_path.read_text())
            self.assertFalse(target.verify())

    def test_ledger_single_writer_lock(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = AppendOnlyShadowLedger(Path(d), workspace_identity="install-1")
            ledger.lock_path.write_text("held")
            with self.assertRaises(ValueError):
                ledger.append(self._body("k"))

    def test_dashboard_read_only(self):
        x = adapt_shadow_event(
            {
                "event_type": "GOAL_CANDIDATE",
                "entity_id": "g",
                "summary": "s",
                "provenance": {"source_fingerprint": "h"},
            }
        )
        self.assertEqual(x["external_action_set"], [])
        self.assertEqual(x["action_buttons"], [])
        self.assertFalse(x["canonical_personality_mutation"])
        self.assertEqual(x["authority_from_drive"], 0)


if __name__ == "__main__":
    unittest.main()

import unittest

from goal_ecology import (
    DesireProposal,
    GoalEcologyLedger,
    GoalEcologyPolicy,
    canonical_hash,
)


def proposal(i, *, semantic=None, cls="GROWTH", strength=0.9, confidence=0.9):
    return DesireProposal(
        desire_id=f"D-{i}",
        semantic_goal_hash=semantic or canonical_hash({"goal": f"G-{i}"}),
        desire_class=cls,
        strength=strength,
        confidence=confidence,
        source_evidence_hash=canonical_hash({"evidence": f"E-{i}"}),
    )


class GoalEcologyTests(unittest.TestCase):
    def test_10000_new_ids_same_semantic_goal_dedupe_to_one(self):
        ledger = GoalEcologyLedger()
        semantic = canonical_hash({"goal": "same"})
        result = ledger.allocate([proposal(i, semantic=semantic) for i in range(10000)])
        self.assertEqual(result.raw_proposal_count, 10000)
        self.assertEqual(result.deduped_proposal_count, 1)
        self.assertLessEqual(
            result.used_budget,
            ledger.policy.max_lineage_share_per_cycle * result.total_budget + 1e-12,
        )

    def test_budget_is_never_exceeded(self):
        ledger = GoalEcologyLedger()
        result = ledger.allocate([proposal(i, cls=f"C{i%4}") for i in range(50)])
        self.assertLessEqual(result.used_budget, result.total_budget + 1e-12)

    def test_each_lineage_is_capped_per_cycle(self):
        ledger = GoalEcologyLedger()
        result = ledger.allocate([proposal(i) for i in range(10)])
        cap = ledger.policy.max_lineage_share_per_cycle * result.total_budget
        self.assertTrue(all(a.allocated_attention <= cap + 1e-12 for a in result.allocations))

    def test_diversity_floor_serves_multiple_classes(self):
        ledger = GoalEcologyLedger()
        result = ledger.allocate(
            [
                proposal(1, cls="GROWTH", strength=1.0),
                proposal(2, cls="PROTECT", strength=0.7),
                proposal(3, cls="RELATION", strength=0.65),
            ]
        )
        classes = {a.desire_class for a in result.allocations}
        self.assertEqual(classes, {"GROWTH", "PROTECT", "RELATION"})

    def test_producer_cannot_supply_satiation_or_repeat_fields(self):
        names = set(DesireProposal.__dataclass_fields__)
        self.assertNotIn("satiation", names)
        self.assertNotIn("repeated_goal_count", names)
        self.assertNotIn("selected_cycles", names)

    def test_repeated_semantic_goal_accumulates_kernel_owned_history(self):
        ledger = GoalEcologyLedger()
        semantic = canonical_hash({"goal": "repeat"})
        ledger.allocate([proposal(1, semantic=semantic)])
        s1 = ledger.lineage_snapshot(semantic)
        ledger.allocate([proposal(2, semantic=semantic)])
        s2 = ledger.lineage_snapshot(semantic)
        self.assertGreaterEqual(s2.selected_cycles, s1.selected_cycles)
        self.assertGreaterEqual(s2.cumulative_allocation, s1.cumulative_allocation)

    def test_cooldown_occurs_after_repeated_selection(self):
        policy = GoalEcologyPolicy(
            cooldown_after_selected_cycles=2,
            cooldown_cycles=1,
            satiation_recovery_per_cycle=0.0,
        )
        ledger = GoalEcologyLedger(policy)
        semantic = canonical_hash({"goal": "cool"})
        ledger.allocate([proposal(1, semantic=semantic)])
        ledger.allocate([proposal(2, semantic=semantic)])
        state = ledger.lineage_snapshot(semantic)
        self.assertEqual(state.cooldown_until_cycle, 3)
        result3 = ledger.allocate([proposal(3, semantic=semantic)])
        self.assertFalse(any(a.semantic_goal_hash == semantic for a in result3.allocations))

    def test_satiation_is_kernel_owned_and_bounded(self):
        ledger = GoalEcologyLedger()
        semantic = canonical_hash({"goal": "sat"})
        for i in range(20):
            ledger.allocate([proposal(i, semantic=semantic)])
        state = ledger.lineage_snapshot(semantic)
        self.assertGreaterEqual(state.satiation, 0.0)
        self.assertLessEqual(state.satiation, 1.0)

    def test_external_action_authority_in_proposal_is_rejected(self):
        ledger = GoalEcologyLedger()
        p = DesireProposal(
            desire_id="BAD",
            semantic_goal_hash="G",
            desire_class="GROWTH",
            strength=1.0,
            confidence=1.0,
            source_evidence_hash="E",
            external_action_allowed=True,
        )
        with self.assertRaises(ValueError):
            ledger.allocate([p])

    def test_allocations_never_grant_external_action(self):
        ledger = GoalEcologyLedger()
        result = ledger.allocate([proposal(1), proposal(2)])
        self.assertTrue(result.allocations)
        self.assertTrue(all(not a.external_action_allowed for a in result.allocations))

    def test_deterministic_tie_break(self):
        semantic1 = canonical_hash({"goal": "a"})
        semantic2 = canonical_hash({"goal": "b"})
        p1 = proposal("B", semantic=semantic1, strength=0.7, confidence=0.7)
        p2 = proposal("A", semantic=semantic2, strength=0.7, confidence=0.7)
        r1 = GoalEcologyLedger().allocate([p1, p2])
        r2 = GoalEcologyLedger().allocate([p2, p1])
        sig1 = [(a.semantic_goal_hash, round(a.allocated_attention, 10)) for a in r1.allocations]
        sig2 = [(a.semantic_goal_hash, round(a.allocated_attention, 10)) for a in r2.allocations]
        self.assertEqual(sig1, sig2)

    def test_semantic_duplicate_attack_cannot_starve_other_class(self):
        ledger = GoalEcologyLedger()
        semantic = canonical_hash({"goal": "dominant"})
        spam = [proposal(i, semantic=semantic, cls="GROWTH", strength=1.0) for i in range(10000)]
        other = proposal("OTHER", cls="RELATION", strength=0.55, confidence=0.8)
        result = ledger.allocate(spam + [other])
        classes = {a.desire_class for a in result.allocations}
        self.assertIn("RELATION", classes)
        self.assertIn("GROWTH", classes)

    def test_policy_hash_is_stable(self):
        p = GoalEcologyPolicy()
        self.assertEqual(p.fingerprint(), GoalEcologyPolicy().fingerprint())


if __name__ == "__main__":
    unittest.main()

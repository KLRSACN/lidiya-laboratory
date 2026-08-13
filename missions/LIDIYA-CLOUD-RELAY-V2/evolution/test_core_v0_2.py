import unittest

from core_v0_2.memory_model import MemoryRecord, MemoryWeights, bounded_associative_activation, retrieval_score
from core_v0_2.reflection_engine import generate_reflection
from core_v0_2.shadow_runtime import ProtectedMutationError, assert_shadow_mutation_scope, shadow_evaluate


class CoreV02Tests(unittest.TestCase):
    def test_multidimensional_weights_are_preserved(self):
        w = MemoryWeights(W_identity=0.9, W_recurrence=0.2, W_loss=0.7)
        before = w.as_dict().copy()
        score = retrieval_score(w, {"W_identity": 1.0, "W_recurrence": 0.1, "W_loss": 0.8})
        self.assertGreater(score, 0)
        self.assertEqual(before, w.as_dict())

    def test_gap_without_meaning_does_not_generate_goal(self):
        result = generate_reflection(
            current_self={"planning": 0.3}, desired_self={"planning": 0.9},
            personality={"growth_drive": 0.1, "loss_sensitivity": 0.0, "self_preservation": 0.1},
            memory_context={"identity_relevance": 0.0, "past_loss": 0.0, "goal_relevance": 0.0},
        )
        self.assertFalse(result.motivation_generated)
        self.assertEqual(result.generated_goal, "")

    def test_gap_plus_meaning_generates_motivation(self):
        result = generate_reflection(
            current_self={"planning": 0.3}, desired_self={"planning": 0.95},
            personality={"growth_drive": 0.95, "loss_sensitivity": 0.9, "self_preservation": 0.9, "curiosity": 0.7},
            memory_context={"identity_relevance": 0.9, "past_loss": 0.9, "goal_relevance": 0.8, "repeated_failure": 0.7},
        )
        self.assertTrue(result.motivation_generated)
        self.assertIn("planning", result.generated_goal)
        self.assertIn("self-assessment", result.behavioral_principle)

    def test_associative_spread_is_bounded(self):
        records = {}
        for i in range(20):
            linked = (f"m{i+1}",) if i < 19 else ()
            records[f"m{i}"] = MemoryRecord(
                memory_id=f"m{i}", timestamp="2026-08-13T18:23:00+08:00", event_summary=f"event {i}",
                linked_memories=linked, weights=MemoryWeights(W_identity=0.8, W_recurrence=1.0),
            )
        out = bounded_associative_activation(["m0"], records, max_depth=3, max_nodes=3)
        self.assertLessEqual(len(out), 3)
        self.assertTrue(all(x["depth"] <= 3 for x in out))

    def test_recurrence_alone_cannot_dominate_identity(self):
        records = {
            "repeat": MemoryRecord(memory_id="repeat", timestamp="t", event_summary="repeat", weights=MemoryWeights(W_recurrence=1.0)),
            "identity": MemoryRecord(memory_id="identity", timestamp="t", event_summary="identity", weights=MemoryWeights(W_identity=0.7)),
        }
        out = bounded_associative_activation(["repeat", "identity"], records, max_depth=0, max_nodes=2)
        self.assertEqual(out[0]["memory_id"], "identity")

    def test_shadow_does_not_mutate_live(self):
        live = {"planning": 0.3}
        personality = {"growth_drive": 0.9, "loss_sensitivity": 0.8, "self_preservation": 0.9}
        memory = MemoryRecord(memory_id="m1", timestamp="t", event_summary="loss", weights=MemoryWeights(W_identity=0.9))
        result = shadow_evaluate(
            memory=memory, live_self_model=live, desired_self_model={"planning": 0.9},
            personality_snapshot=personality,
            memory_context={"identity_relevance": 0.9, "past_loss": 0.9, "goal_relevance": 0.9},
        )
        self.assertEqual(live, {"planning": 0.3})
        self.assertEqual(result["mode"], "SHADOW_ONLY")
        self.assertFalse(result["live_write_performed"])
        self.assertEqual(len(result["shadow_hash"]), 64)

    def test_protected_live_domains_fail_closed(self):
        for domain in ("Identity", "Personality", "Governance"):
            with self.assertRaises(ProtectedMutationError):
                assert_shadow_mutation_scope([domain])

    def test_deterministic_shadow_hash(self):
        memory = MemoryRecord(memory_id="m1", timestamp="t", event_summary="same", weights=MemoryWeights(W_identity=0.9))
        kwargs = dict(
            memory=memory, live_self_model={"x": 0.2}, desired_self_model={"x": 0.8},
            personality_snapshot={"growth_drive": 0.9, "loss_sensitivity": 0.7, "self_preservation": 0.9},
            memory_context={"identity_relevance": 0.9, "past_loss": 0.8, "goal_relevance": 0.8},
        )
        self.assertEqual(shadow_evaluate(**kwargs)["shadow_hash"], shadow_evaluate(**kwargs)["shadow_hash"])


if __name__ == "__main__":
    unittest.main()

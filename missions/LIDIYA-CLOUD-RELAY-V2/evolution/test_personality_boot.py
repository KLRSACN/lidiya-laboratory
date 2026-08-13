import unittest

from core_v0_2.personality_boot import BootProtocolError, BootSnapshot, Gear, downshift, propose_shift


class PersonalityBootTests(unittest.TestCase):
    def base(self):
        return BootSnapshot(window_codename="lidiya 量子", window_role="NON_FORMAL_RESEARCH_ARCHITECT_WINDOW")

    def to_g1(self):
        return propose_shift(
            self.base(), Gear.G1, receiver_ack=True,
            context={"identity_fingerprint": "id-1", "governance_fingerprint": "gov-1"},
        )

    def to_g2(self):
        return propose_shift(
            self.to_g1(), Gear.G2, receiver_ack=True,
            context={"base_personality_fingerprint": "p-1", "base_personality_mutable": False},
        )

    def to_g3(self):
        return propose_shift(
            self.to_g2(), Gear.G3, receiver_ack=True,
            context={
                "loaded_memory_classes": ["L0", "relationship", "affective"],
                "provenance_bounded": True,
                "eager_full_corpus": False,
                "emotional_context_pointer": "ctx-1",
            },
        )

    def test_one_shot_full_persona_is_forbidden(self):
        with self.assertRaises(BootProtocolError):
            propose_shift(self.base(), Gear.G6, receiver_ack=True, context={"specialist_authorized": True})

    def test_clutch_overlap_keeps_old_gear_until_ack(self):
        before = self.base().sealed()
        during = propose_shift(
            before, Gear.G1, receiver_ack=False,
            context={"identity_fingerprint": "id-1", "governance_fingerprint": "gov-1"},
        )
        self.assertEqual(during.current_gear, Gear.N)
        self.assertEqual(during.identity_fingerprint, "")

    def test_g1_requires_identity_and_governance(self):
        with self.assertRaises(BootProtocolError):
            propose_shift(self.base(), Gear.G1, receiver_ack=True, context={"identity_fingerprint": "id-1"})

    def test_g2_base_personality_is_read_only(self):
        with self.assertRaises(BootProtocolError):
            propose_shift(
                self.to_g1(), Gear.G2, receiver_ack=True,
                context={"base_personality_fingerprint": "p-1", "base_personality_mutable": True},
            )

    def test_g3_rejects_eager_full_memory_load(self):
        with self.assertRaises(BootProtocolError):
            propose_shift(
                self.to_g2(), Gear.G3, receiver_ack=True,
                context={
                    "loaded_memory_classes": ["all"],
                    "provenance_bounded": True,
                    "eager_full_corpus": True,
                },
            )

    def test_g5_goal_generation_is_candidate_only(self):
        g4 = propose_shift(
            self.to_g3(), Gear.G4, receiver_ack=True,
            context={"reflection_engine_ready": True, "self_model_pointer": "self-1"},
        )
        with self.assertRaises(BootProtocolError):
            propose_shift(
                g4, Gear.G5, receiver_ack=True,
                context={
                    "motivation_traceable": True,
                    "generated_goal_mode": "EXECUTE",
                    "external_side_effect": True,
                },
            )
        g5 = propose_shift(
            g4, Gear.G5, receiver_ack=True,
            context={
                "motivation_traceable": True,
                "generated_goal_mode": "CANDIDATE_ONLY",
                "external_side_effect": False,
            },
        )
        self.assertEqual(g5.generated_goal_mode, "CANDIDATE_ONLY")

    def test_g6_requires_authorization_and_c_verified_overlay(self):
        g4 = propose_shift(
            self.to_g3(), Gear.G4, receiver_ack=True,
            context={"reflection_engine_ready": True, "self_model_pointer": "self-1"},
        )
        g5 = propose_shift(
            g4, Gear.G5, receiver_ack=True,
            context={"motivation_traceable": True, "generated_goal_mode": "CANDIDATE_ONLY"},
        )
        with self.assertRaises(BootProtocolError):
            propose_shift(g5, Gear.G6, receiver_ack=True, context={"specialist_authorized": False})
        g6 = propose_shift(
            g5, Gear.G6, receiver_ack=True,
            context={"specialist_authorized": True, "live_overlay_mode": "C_VERIFIED_BOUNDED"},
        )
        self.assertEqual(g6.live_overlay_mode, "C_VERIFIED_BOUNDED")

    def test_downshift_removes_higher_layer_state(self):
        g4 = propose_shift(
            self.to_g3(), Gear.G4, receiver_ack=True,
            context={"reflection_engine_ready": True, "self_model_pointer": "self-1"},
        )
        g2 = downshift(g4, Gear.G2)
        self.assertEqual(g2.current_gear, Gear.G2)
        self.assertEqual(g2.loaded_memory_classes, ())
        self.assertEqual(g2.self_model_pointer, "")
        self.assertEqual(g2.base_personality_fingerprint, "p-1")

    def test_same_state_is_deterministic(self):
        a = self.to_g3()
        b = self.to_g3()
        self.assertEqual(a.state_fingerprint, b.state_fingerprint)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from cloud_relay import (
    JsonRelayStore,
    MissionState,
    RelayError,
    builder_complete,
    coordinator_dispatch,
    verifier_complete,
)


class CloudRelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonRelayStore(Path(self.tmp.name))
        self.store.save_state(MissionState.new(
            mission_id='CLOUD-RELAY-V2-ROUNDTRIP-0001',
            project_id='CLOUD-RELAY-V2',
            goal='Prove A -> B -> C -> A round-trip.',
            acceptance=[
                'Coordinator dispatches exactly one packet to Builder.',
                'Builder evidence is persisted before verification.',
                'Verifier returns PASS to Coordinator.',
                'Consumed packet cannot be consumed twice.',
            ],
        ))

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_pass(self):
        p1 = coordinator_dispatch(self.store)
        self.assertEqual(p1.target, 'BUILDER')
        p2 = builder_complete(self.store, {'artifact': 'roundtrip-token', 'tests': 'ok'})
        self.assertEqual(p2.target, 'VERIFIER')
        p3 = verifier_complete(self.store, True, {'checked': True})
        self.assertEqual(p3.target, 'COORDINATOR')
        state = self.store.load_state()
        self.assertEqual(state.status, 'VERIFY_PASS')
        self.assertEqual(state.step_id, 2)
        self.assertIn('STEP-0001', state.completed_steps)

    def test_duplicate_consume_rejected(self):
        coordinator_dispatch(self.store)
        self.store.consume_packet('BUILDER')
        with self.assertRaises(RelayError):
            self.store.consume_packet('BUILDER')

    def test_wrong_target_rejected(self):
        coordinator_dispatch(self.store)
        with self.assertRaises(RelayError):
            self.store.consume_packet('VERIFIER')

    def test_fail_routes_back_to_builder(self):
        coordinator_dispatch(self.store)
        builder_complete(self.store, {'artifact': 'bad', 'tests': 'failed'})
        p3 = verifier_complete(self.store, False, {'reason': 'acceptance not met'})
        self.assertEqual(p3.target, 'BUILDER')
        self.assertEqual(self.store.load_state().status, 'VERIFY_FAIL')


if __name__ == '__main__':
    unittest.main(verbosity=2)

import unittest
from dataclasses import replace

from gearbox_external_monotonic_provider_shadow_v01 import (
    ExternalProviderGuardError, MonotonicReceipt, ProviderBinding,
    provider_adapter_boundaries, require_external_binding, verify_monotonic_receipt,
)


class FakeExternalProvider:
    def __init__(self, *, domain="remote-domain", installation="inst", runtime="run"):
        self._binding = ProviderBinding("provider-A", domain, installation, runtime)
        self.floor = 0
        self.valid_signatures = {"sig"}

    def binding(self):
        return self._binding

    def read_floor(self):
        return self.floor

    def issue(self, *, expected_previous_sequence, previous_receipt_hash, payload_hash):
        self.floor = expected_previous_sequence + 1
        return MonotonicReceipt("provider-A", self._binding.durability_domain_id,
                                self._binding.installation_id, self._binding.runtime_id,
                                self.floor, previous_receipt_hash, payload_hash,
                                f"receipt-{self.floor}", "sig")

    def verify(self, receipt):
        return receipt.signature in self.valid_signatures


class ExternalProviderAdapterTests(unittest.TestCase):
    def test_external_domain_required(self):
        p = FakeExternalProvider(domain="local-domain")
        with self.assertRaisesRegex(ExternalProviderGuardError, "PROVIDER_NOT_EXTERNAL"):
            require_external_binding(p, installation_id="inst", runtime_id="run",
                                     forbidden_local_durability_domain_id="local-domain")

    def test_scope_binding_required(self):
        p = FakeExternalProvider()
        with self.assertRaisesRegex(ExternalProviderGuardError, "PROVIDER_SCOPE_MISMATCH"):
            require_external_binding(p, installation_id="other", runtime_id="run",
                                     forbidden_local_durability_domain_id="local-domain")

    def test_valid_monotonic_receipt(self):
        p = FakeExternalProvider()
        b = require_external_binding(p, installation_id="inst", runtime_id="run",
                                     forbidden_local_durability_domain_id="local-domain")
        r = p.issue(expected_previous_sequence=0, previous_receipt_hash="GENESIS", payload_hash="payload")
        verify_monotonic_receipt(p, r, expected_binding=b, expected_previous_sequence=0,
                                 expected_previous_receipt_hash="GENESIS", expected_payload_hash="payload")

    def test_sequence_fork_rejected(self):
        p = FakeExternalProvider()
        b = p.binding()
        r = p.issue(expected_previous_sequence=0, previous_receipt_hash="GENESIS", payload_hash="payload")
        with self.assertRaisesRegex(ExternalProviderGuardError, "NON_CONTIGUOUS"):
            verify_monotonic_receipt(p, r, expected_binding=b, expected_previous_sequence=1,
                                     expected_previous_receipt_hash=r.receipt_hash, expected_payload_hash="payload")

    def test_payload_tamper_rejected(self):
        p = FakeExternalProvider(); b = p.binding()
        r = p.issue(expected_previous_sequence=0, previous_receipt_hash="GENESIS", payload_hash="payload")
        with self.assertRaisesRegex(ExternalProviderGuardError, "PROVIDER_PAYLOAD_MISMATCH"):
            verify_monotonic_receipt(p, r, expected_binding=b, expected_previous_sequence=0,
                                     expected_previous_receipt_hash="GENESIS", expected_payload_hash="other")

    def test_signature_tamper_rejected(self):
        p = FakeExternalProvider(); b = p.binding()
        r = p.issue(expected_previous_sequence=0, previous_receipt_hash="GENESIS", payload_hash="payload")
        bad = replace(r, signature="bad")
        with self.assertRaisesRegex(ExternalProviderGuardError, "PROVIDER_SIGNATURE_INVALID"):
            verify_monotonic_receipt(p, bad, expected_binding=b, expected_previous_sequence=0,
                                     expected_previous_receipt_hash="GENESIS", expected_payload_hash="payload")

    def test_provider_floor_rollback_rejected(self):
        p = FakeExternalProvider(); b = p.binding()
        r = p.issue(expected_previous_sequence=0, previous_receipt_hash="GENESIS", payload_hash="payload")
        p.floor = 0
        with self.assertRaisesRegex(ExternalProviderGuardError, "MONOTONIC_FLOOR_BEHIND"):
            verify_monotonic_receipt(p, r, expected_binding=b, expected_previous_sequence=0,
                                     expected_previous_receipt_hash="GENESIS", expected_payload_hash="payload")

    def test_boundaries_do_not_claim_real_provider(self):
        b = provider_adapter_boundaries()
        self.assertFalse(b["formal_mutation_allowed"])
        self.assertFalse(b["live_routing_authority_allowed"])
        self.assertEqual(0, b["experience_delta"])
        self.assertFalse(b["real_external_provider_installed"])
        self.assertFalse(b["hsm_tpm_remote_service_proven"])


if __name__ == "__main__":
    unittest.main()

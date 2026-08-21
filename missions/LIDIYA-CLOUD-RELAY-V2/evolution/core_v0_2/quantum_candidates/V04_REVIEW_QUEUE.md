# V04 Dependency Review Queue

Before implementation, review these existing V03 dependencies without modifying them:

- gearbox_external_monotonic_provider_shadow_v01.py
- gearbox_secretary_runtime_freshness_shadow_v02.py
- gearbox_authority_experience_signer_shadow_v01.py
- GEARBOX_CLOCK_EPOCH_RECOVERY_SHADOW_V03_CONTRACT.json
- test_gearbox_clock_epoch_recovery_shadow_v03.py
- test_gearbox_clock_epoch_recovery_shadow_v03_w01_adversarial.py

Acceptance design must preserve all existing passing regression behavior while closing the three W01 fail-closed gaps.

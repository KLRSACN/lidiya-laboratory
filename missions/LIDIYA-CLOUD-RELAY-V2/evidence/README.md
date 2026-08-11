# Evidence ledger

This directory is append-oriented evidence for Cloud Relay v2.

Each role should prefer creating a new evidence file per transition rather than rewriting old evidence.

Suggested names:

- `A_STEP-0001_<timestamp>.json`
- `B_STEP-0001_<timestamp>.json`
- `C_STEP-0001_<timestamp>.json`

Minimum fields: mission_id, step_id, packet_id, role, source refs/SHAs, checks performed, observed result, timestamp, and any unresolved uncertainty.

Never store credentials, tokens, secrets, private keys, payment data, or unrelated personal data here.

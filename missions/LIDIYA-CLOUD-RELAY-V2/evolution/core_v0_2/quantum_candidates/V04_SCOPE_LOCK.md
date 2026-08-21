# V04 Scope Lock

Only the final re-entry trust-root boundary is in scope.

Out of scope for V04:
- personality or memory changes
- Hermes/Navigator integration changes
- formal mission state mutation
- live routing authority
- production key/HSM/TPM claims
- cleanup or deletion of V03 files

This prevents the W01 repair from contaminating unrelated development lines.

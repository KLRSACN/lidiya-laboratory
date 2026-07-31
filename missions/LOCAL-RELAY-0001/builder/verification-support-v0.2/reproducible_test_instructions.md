# Reproducible Test Instructions

## Environment

- Python 3.11 or newer
- Standard library only
- Candidate commit: `35988ad594d725aed4e5f907ba1d050385135a6f`

## Working directory

Use this repository-relative directory:

```text
missions/LOCAL-RELAY-0001/builder/candidate-v0.2/
```

Do not substitute credentials or a private absolute path.

## Run all tests

```bash
python -m unittest -v test_local_relay_v0_2.py
```

## Run one test

```bash
python -m unittest -v test_local_relay_v0_2.CrashConsistencyTests.test_19_restart_recovers_outbox_only
```

## Expected result

```text
total=24
passed=24
failed=0
exit_code=0
```

The suite uses temporary isolated runtime roots and requires no network, credentials, Live Trigger, browser control, GitHub polling, or external AI API.

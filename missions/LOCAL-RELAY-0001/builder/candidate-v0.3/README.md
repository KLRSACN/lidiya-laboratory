# Local Relay Dispatcher candidate v0.3

Protocol-alignment candidate based on v0.2. Adds strict packet validation, authorized runtime-root allowlisting, lease-generation fencing, recovery counters, protocol checkpoint/state schemas, and completed-registry `outbox_path`.

Run:

```bash
python -m unittest -v test_local_relay_v0_3.py
```

Expected: 36 tests, all passing. This is a candidate only.

# Local Relay Dispatcher candidate v0.3

Reconstructed from committed v0.2 and review mappings. Supports only local `WRITE_TEXT`; no live trigger.

## Run

`python -m unittest -v test_local_relay_v0_3.py`

## Auditor mapping

- `claim()` -> `LocalRelayDispatcherV03.claim`
- `heartbeat()` -> `LocalRelayDispatcherV03.heartbeat`
- `submit_result()` -> `LocalRelayDispatcherV03.submit_result`
- `recover()` -> `LocalRelayDispatcherV03.recover`
- `read_task_state()` -> same name
- `read_checkpoint()` -> same name
- `read_completed_record()` -> same name

Fault injection is disabled unless the explicit test-only `fault` argument is supplied.

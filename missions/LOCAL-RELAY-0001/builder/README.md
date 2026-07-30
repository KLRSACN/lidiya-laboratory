# Local Relay Dispatcher v0.1

Filesystem-only local relay candidate for `LOCAL-RELAY-0001`.

## Runtime flow

`runtime/inbox -> atomic os.replace claim -> runtime/running -> runtime/outbox or runtime/failed`

Recovery scans persisted running files and uses lease timestamps from disk. Corrupt or unsupported packets are moved to quarantine. JSON writes use a temporary file, `fsync`, and atomic `os.replace`.

## Safety boundaries

- All paths are resolved beneath Runtime Root.
- `../` and absolute output paths are rejected.
- Only `WRITE_TEXT` is implemented.
- No browser, ChatGPT window, external AI API, GitHub polling, shell action, or HOME modification.

## Run tests

```bash
python test_local_relay.py
```

## Worker stub

```bash
python relay_worker_stub.py ./runtime --worker-id WINDOW-01
```

The stub performs one recovery/claim/execute pass and exits.

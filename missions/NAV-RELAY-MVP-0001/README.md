# NAV-RELAY-MVP-0001

A two-window semi-autonomous text relay MVP built from Coordinator, SQLite Relay, Scheduler, and a Playwright/CDP Navigator.

## Implemented components

- `relay_protocol.py`
  - Parses TARGET, ACTION, and WAKE_AFTER fields.
  - Extracts content between RELAY_OUTPUT_BEGIN and RELAY_OUTPUT_END.
- `relay_mvp.py`
  - SQLite mailbox and window registry.
  - Message queue and scheduled wake processing.
  - Explicit message lifecycle states.
- `coordinator_mvp.py`
  - Routes work according to worker STATE.
- `navigator_adapter.py`
  - Connects to Chrome through CDP debug ports.
  - Locates ChatGPT pages by URL and marker or WINDOW-NN title token.
  - Pastes and sends relay messages.
  - Detects new Assistant responses by message-count increase.
  - Waits for stable output and ingests the response.
- `test_mvp.py`
- `test_navigator_adapter.py`

## Message lifecycle

| State | Meaning |
|---|---|
| `PENDING` | Not yet sent to the target window |
| `AWAITING_RESPONSE` | Sent and waiting for an Assistant response |
| `COMPLETED` | Complete response received |
| `TIMED_OUT` | Sent but response wait expired; no automatic resend |
| `FAILED` | Connection, targeting, or send failure; no automatic resend |

## Verified environment

- WINDOW-00: Coordinator on CDP port 9222.
- WINDOW-01: Builder on CDP port 9223.
- Branch: `nav-relay-mvp-0001`.
- Verified commit: `8b12347d01e50f381e03ab16a97812870a1d07a8`.
- Test result: `15/15 OK`.
- Default response timeout: 300 seconds.

## Run tests

```powershell
& ".\.venv\Scripts\python.exe" -m unittest -v test_mvp.py test_navigator_adapter.py
```

## Register windows

```powershell
& ".\.venv\Scripts\python.exe" .\relay_mvp.py --db .\nav_relay_mvp.sqlite3 register WINDOW-00 COORDINATOR 9222 "[LIDIYA:WINDOW-00]"
& ".\.venv\Scripts\python.exe" .\relay_mvp.py --db .\nav_relay_mvp.sqlite3 register WINDOW-01 BUILDER 9223 "[LIDIYA:WINDOW-01]"
```

## Start Scheduler

```powershell
& ".\.venv\Scripts\python.exe" .\relay_mvp.py --db .\nav_relay_mvp.sqlite3 scheduler --interval 5
```

## Start Navigator

```powershell
& ".\.venv\Scripts\python.exe" .\navigator_adapter.py --db .\nav_relay_mvp.sqlite3 --mission-id NAV-RELAY-MVP-0001 --interval 5 --response-timeout 300 WINDOW-00 WINDOW-01
```

Run Scheduler and Navigator in separate terminals. Chrome must remain signed in, reachable through the registered CDP ports, and connected to the network.

## Relay response format

```text
[RELAY_READY]
[TARGET:WINDOW-00]
[ACTION:SEND]
[WAKE_AFTER:5]
[RELAY_OUTPUT_BEGIN]
STATE=NAVIGATOR_ROUNDTRIP_BUILDER_ACK
SOURCE=WINDOW-01
TARGET=WINDOW-00
ROUNDTRIP_TOKEN=<UNIQUE_TOKEN>
READY_FOR_NEXT_TASK=true
[RELAY_OUTPUT_END]
```

## Safety behavior

- Relay payloads are not executed as arbitrary shell commands.
- Timeouts and failures do not automatically resend messages.
- Playwright disconnects from CDP but does not close the user's Chrome.
- Non-ChatGPT pages are excluded from body scanning.
- Confirm there are no stale PENDING or AWAITING_RESPONSE messages before live operation.
- Do not use force-push.

## Current state

Code and tests are pushed at commit `8b12347`.
Navigator and Scheduler are intentionally stopped while documentation and final packaging are completed.

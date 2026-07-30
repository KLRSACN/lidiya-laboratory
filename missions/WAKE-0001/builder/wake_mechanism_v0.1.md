# Wake Mechanism v0.1

## 1. Purpose

Wake Mechanism v0.1 defines the minimum verifiable lifecycle for a LIDIYA Worker:

`WAIT_TRIGGER -> RUNNING -> RELAY_READY -> WAIT_TRIGGER`

It proves that a worker can validate a trigger, execute only the assigned Builder objective,
produce evidence, generate a relay packet, and reset to an idle state.

## 2. Worker State Machine

### States

| State | Meaning | Allowed next states |
|---|---|---|
| `WAIT_TRIGGER` | Worker is idle and accepts only a complete trigger packet targeted to itself. | `RUNNING`, `WAIT_TRIGGER` |
| `RUNNING` | Trigger was validated and the assigned Builder work is executing. | `RELAY_READY`, `BLOCKED` |
| `RELAY_READY` | Work stopped with a relay packet and evidence ready for MAIN-LIDIYA. | `WAIT_TRIGGER` |
| `BLOCKED` | Execution cannot continue; blocker evidence and minimum next action are required. | `RELAY_READY` |
| `WAIT_TRIGGER` | Final reset state after relay emission. | `RUNNING`, `WAIT_TRIGGER` |

### Transition rules

1. `WAIT_TRIGGER -> RUNNING`
   - Required trigger fields are present.
   - `TARGET == WORKER-01`.
   - `ACTION == START`.
   - `MISSION_ID` and `TOKEN` are non-empty.
   - Worker stores a checkpoint before execution.

2. `RUNNING -> RELAY_READY`
   - Minimum verifiable Builder output exists.
   - Evidence contains at least one inspectable artifact, execution result, test result, or concrete path.
   - Relay packet is complete.

3. `RUNNING -> BLOCKED`
   - A blocker prevents the assigned objective from reaching the minimum verifiable result.
   - Worker records `BLOCKER`, `EVIDENCE`, and `MINIMUM_NEXT_ACTION`.

4. `BLOCKED -> RELAY_READY`
   - A `BLOCKED` relay packet has been prepared.

5. `RELAY_READY -> WAIT_TRIGGER`
   - Relay has been emitted.
   - `MISSION_ID` and `TOKEN` are cleared.
   - `HEARTBEAT` returns to `READY`.

## 3. Trigger Packet Schema

Required fields:

```text
MISSION_ID: non-empty string
TARGET: exact worker identifier
ACTION: START
TOKEN: non-empty string
OBJECTIVE: non-empty string
SUCCESS_CRITERIA: non-empty list or text
EVIDENCE_REQUIRED: non-empty list or text
```

Optional fields:

```text
PRIORITY
SYSTEM_MODE
MISSION_STATUS
```

Validation result:

```text
VALID
INVALID_TRIGGER
WRONG_TARGET
```

Invalid triggers never enter `RUNNING`.

## 4. Relay Packet Schema

Required fields:

```text
FROM
TO
MISSION_ID
TOKEN
ROLE
STATUS
HEARTBEAT
OBJECTIVE_RECEIVED
WORK_COMPLETED
ARTIFACTS
EVIDENCE
VERIFICATION_METHOD
KNOWN_ISSUES
FILES_OR_LOCATIONS
RECOMMENDED_NEXT_WORKER
NEXT_ACTION
CHECKPOINT
```

`STATUS` must be one of:

```text
DONE
PARTIAL
BLOCKED
FAILED
```

A Worker may report `DONE` for its assigned Builder work, but does not declare the whole mission complete.

## 5. Progress Token Rules

The progress token is a mission-scoped monotonic execution marker.

Format:

```text
<MISSION_ID>:<TOKEN>:P<four-digit-step>
```

Example:

```text
WAKE-0001:BOOTSTRAP-0001:P0003
```

Rules:

1. Start at `P0000` after trigger validation.
2. Increment exactly once after every durable state change or artifact checkpoint.
3. Never decrement or reuse a progress token within the same mission and token pair.
4. Persist the latest progress token in `CHECKPOINT`.
5. Duplicate trigger with the same `MISSION_ID`, `TOKEN`, and completed progress token must not repeat side effects.
6. A trigger with the same `MISSION_ID` but a different `TOKEN` is treated as a new assignment only after MAIN-LIDIYA authorization.
7. On recovery, resume from the highest persisted progress token.
8. Relay emission records the final progress token.
9. Resetting to `WAIT_TRIGGER` clears active mission fields but does not erase the emitted checkpoint record.

## 6. Valid Trigger Example

```text
MISSION_ID = WAKE-0001
TARGET = WORKER-01
ACTION = START
TOKEN = BOOTSTRAP-0001
OBJECTIVE = Build and verify Wake Mechanism v0.1.
SUCCESS_CRITERIA = State machine, trigger schema, relay schema, progress token rules, simulation.
EVIDENCE_REQUIRED = Specification, valid trigger, relay example, transition log, handoff checkpoint.
```

## 7. Completed Relay Example

```text
[RELAY]

FROM = WORKER-01
TO = MAIN-LIDIYA
MISSION_ID = WAKE-0001
TOKEN = BOOTSTRAP-0001
ROLE = BUILDER
STATUS = DONE
HEARTBEAT = WAIT

OBJECTIVE_RECEIVED = Build and verify Wake Mechanism v0.1.

WORK_COMPLETED =
- Created the Wake Mechanism v0.1 specification.
- Created an executable state-machine simulation.
- Executed the simulation and recorded the transition log.
- Produced a WORKER-02 handoff checkpoint.

ARTIFACTS =
- wake_mechanism_v0.1.md
- simulate_wake.py
- simulation_result.json
- state_transition.log
- worker02_checkpoint.json

EVIDENCE =
- Simulation assertion passed.
- Final state is WAIT_TRIGGER.
- Final heartbeat is READY.
- Transition sequence is WAIT_TRIGGER -> RUNNING -> RELAY_READY -> WAIT_TRIGGER.

VERIFICATION_METHOD =
Run: python simulate_wake.py
Inspect simulation_result.json and state_transition.log.

KNOWN_ISSUES =
- This version is a local deterministic simulation.
- No external GitHub, window-driver, or cross-process wake event was tested.

FILES_OR_LOCATIONS =
- /mnt/data/wake_mechanism_v0_1/

RECOMMENDED_NEXT_WORKER = WORKER-02

NEXT_ACTION =
WORKER-02 should review schema interoperability and test invalid, duplicate, and blocked triggers.

CHECKPOINT =
WAKE-0001:BOOTSTRAP-0001:P0004

END_RELAY
```

## 8. Verification Boundary

Verified in this deliverable:

- Required trigger validation.
- Required state transition order.
- Progress token increments.
- Relay-ready checkpoint creation.
- Final reset to `WAIT_TRIGGER` and `HEARTBEAT = READY`.

Not verified:

- Real external window wake-up.
- GitHub issue polling.
- Cross-process persistence.
- Windows Window Driver integration.

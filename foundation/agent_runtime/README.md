# Home Bridge Agent Runtime v0.1

Candidate integration layer that adds the missing Agent Loop, Skills, Session, Cron and Tool Dispatcher to Home Bridge.

## Boundaries

- Home Bridge remains the authority for policy, approval, handoff and rollback.
- Agent Runtime may only execute registered tools inside the configured autonomous zone.
- Models propose actions; deterministic code validates and executes them.
- Every step is persisted in SQLite before the next step.
- Cron creates tasks only; it does not bypass approvals.

## Local layout

`D:\lidiya\0.dev_tools\home_bridge_v2\agent_runtime\`

- `runtime.db` — sessions, tasks, attempts and cron state
- `skills\` — versioned skill definitions
- `workspace\` — autonomous working area
- `logs\` — execution logs
- `quarantine\` — blocked or failed outputs

## First execution scope

The first tool set is intentionally narrow:

- list files
- copy files
- move files
- create directories
- calculate SHA256
- write UTF-8 text inside the autonomous zone

Uploads, downloads, browser automation and publication are added only as separate reviewed tools.

## Run

```powershell
python foundation\agent_runtime\agent_runtime.py --root "D:\lidiya\0.dev_tools\home_bridge_v2\agent_runtime" init
python foundation\agent_runtime\agent_runtime.py --root "D:\lidiya\0.dev_tools\home_bridge_v2\agent_runtime" demo
```

## Integration contract

Input task:

```json
{
  "goal": "copy approved files to the backup folder",
  "skill": "safe_file_copy",
  "arguments": {
    "source": "workspace/inbox",
    "destination": "workspace/backup"
  }
}
```

The runtime loads the skill, validates scope, executes one step, verifies the result, stores the session and either continues, retries, escalates or stops.

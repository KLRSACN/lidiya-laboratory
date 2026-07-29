# Lidiya Autonomous Team Mission

## North Star

Build a persistent autonomous engineering team that can receive a goal from 博玄, continue working without requiring him to stay at the terminal, preserve state across sessions, and request human approval only for high-risk or irreversible actions.

## Required outcome

A task must be able to move through this lifecycle without manual copy/paste mediation:

`RECEIVED -> PLANNED -> RUNNING -> VERIFYING -> RETRYING/ESCALATED -> SUCCESS/FAILED/WAITING_APPROVAL`

The system must:

1. Read project handoffs, current state, policies, and prior evidence.
2. Create a bounded execution plan.
3. Execute only allowlisted tools inside approved paths.
4. Persist task, session, attempt, evidence, and result records.
5. Detect failure and ask Hermes for a structured correction plan.
6. Validate that plan before any execution.
7. Retry only within configured bounds.
8. Continue after ChatGPT or terminal windows close.
9. Produce a concise completion report, rollback location, and saved handoff.
10. Ask 博玄 only for approvals, costs, credentials, irreversible actions, publication, or strategic choices.

## Team roles

### 博玄 — Owner and final authority

Defines goals, risk tolerance, budgets, publication decisions, and irreversible approvals. He must not be used as a manual command relay.

### 璃蒂雅 — Architecture and engineering authority

Defines architecture, reviews major changes, resolves ambiguous engineering decisions, and sets policies. The system should provide structured evidence rather than raw terminal transcripts.

### Navigator — Persistent local operator

Owns the task queue and continuous execution loop. It replaces manual PowerShell copy/paste, resumes incomplete work, routes failures, and records every state transition.

### Hermes — Bounded supervisor

Diagnoses failed attempts and returns structured JSON correction plans. Hermes never executes tools directly and never bypasses Home Bridge policy.

### Gemma — Low-cost frontline worker

Handles routine classification, summarization, log interpretation, and standard Skill execution where risk is low.

### Home Bridge — Governance and control plane

Owns permissions, tool allowlists, path boundaries, approvals, update/rollback, evidence, and the authoritative active release.

## Non-negotiable safety contract

- No arbitrary shell by model request.
- No credential reading or transmission.
- No system-area writes without explicit approval.
- No permanent deletion.
- No external publication without approval.
- No modification of immutable baseline releases.
- All retries are bounded.
- Every state transition and tool result is persisted.
- Failure to validate a plan results in STOP or WAITING_APPROVAL, never improvisation.

## Delivery phases

### Phase 1 — Agent Runtime foundation

Status: completed and activated as candidate.

Includes Agent Loop, Skills, SQLite Session/Attempt records, allowlisted tools, path isolation, Cron base, ESCALATE state, self-test, manifest, and rollback.

### Phase 2 — Hermes Supervisor Adapter

Status: in progress.

Includes structured JSON response, allowlist enforcement, path validation, bounded plan length, offline policy tests, live Ollama test, and persistence of supervisor decisions.

### Phase 3 — Persistent Task Queue

Create durable task records with priority, dependencies, approval state, retry limits, lease/heartbeat, and restart recovery.

### Phase 4 — Navigator Loop

Create a long-running local worker that claims tasks, plans, executes, verifies, escalates, resumes after restart, and emits concise progress events.

### Phase 5 — Approval and notification bridge

Provide a minimal channel for 博玄 to approve or reject high-risk actions without remaining at the terminal.

### Phase 6 — Value-producing Skills

Deliver useful end-to-end workflows for software repair, Blender automation, subtitle/video pipelines, system maintenance, and project handoff generation.

## Definition of done

The project is not complete when a model can call a tool. It is complete when 博玄 can submit a real task, leave the computer, and later receive a verified result with evidence, version location, rollback path, and only the approvals that genuinely required him.

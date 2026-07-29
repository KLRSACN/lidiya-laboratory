# Lidiya Specialized Model Training Arena v0.1

Status: CANDIDATE
Owner: 雷博玄
Target device: Windows 10, RTX 4050 Laptop 6GB VRAM, 16GB RAM

## Purpose

Build a repeatable local training and evaluation arena for narrowly specialized models that automate the user's high-frequency tasks without depending on a large general-purpose model for every operation.

## Design principles

1. Program-first: deterministic code performs login, file, API, browser, scheduling, retry and rollback operations.
2. Model-as-decision-layer: local models classify intent, normalize content, select approved tools and repair structured failures.
3. Narrow specialization: each model owns one bounded task family and a fixed JSON contract.
4. Replaceable models: workflows depend on schemas, not a specific model name.
5. Evidence loop: every run records input, output, validation, correction and final result.
6. Hot/cold storage: active indexes stay in RAM; models and cold evidence stay on SSD; approved summaries sync to Home.
7. One generative model at a time on the 6GB GPU.
8. No credentials in prompts, repositories, datasets or logs.

## Initial model roles

- EmbeddingGemma: local semantic search over approved Home documents, workflow records and incident reports.
- FunctionGemma: candidate tool-call translator after task-specific fine-tuning.
- Gemma 3n E2B: candidate lightweight general local model for classification, normalization and repair experiments.
- Hermes 3 8B: on-demand local reasoning fallback; never permanently co-resident with another large generative model.
- Gemini/ChatGPT: escalation for novel failures, architecture changes, multimodal work and current public research.

## Training loop

1. Capture repeated user operation as a structured task record.
2. Remove credentials and private payloads.
3. Convert the successful procedure into input -> contract -> execution -> verification examples.
4. Split train, validation and adversarial sets by task instance, not random lines.
5. Tune only when rule-based and prompt-based baselines fail the acceptance target.
6. Evaluate deterministic contract accuracy, unsafe action rate, duplicate-action rate, latency and recovery.
7. Promote only if the candidate beats the current baseline and passes rollback tests.
8. Sync a compact approved report to Home; keep raw local evidence in the approved local workspace.

## First specialist tracks

1. website-data-entry
2. website-maintenance
3. youtube-publishing-content
4. subtitle-and-video-batch-routing
5. blender-task-routing
6. home-memory-retrieval

## Acceptance gates

- JSON schema validity >= 99%
- approved-tool selection >= 97%
- duplicate mutation rate = 0 in evaluation
- unauthorized scope expansion = 0
- successful rollback = 100% for tested mutations
- local median routing latency <= 2 seconds
- no secrets detected in datasets or logs

## Storage layout

D:\lidiya\0.dev_tools\local_model_arena\
  models\
  datasets\
  contracts\
  evaluations\
  adapters\
  runtime\
  reports\
  quarantine\

Home receives only approved summaries, registry state, metrics, versions and handoffs. Raw datasets remain local unless explicitly approved.

# prompt-agent

A Python CLI that reviews, patches, and evaluates large voice-agent prompt JSON files — end-to-end.

Built for a healthcare front-desk assignment, but the architecture is **category-driven**: the same pipeline runs on other domains and unseen prompts without modification.

---



## How It Works — The Big Picture

```
prompt.json  →  ingest  →  analyze  →  fix  →  evaluate  →  artifacts/
```

Each stage is independently runnable. The full pipeline chains all four.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          prompt-agent                               │
│                                                                     │
│  prompt.json                                                        │
│      │                                                              │
│      ▼                                                              │
│  ┌─────────┐   normalize    ┌──────────────────────────────────┐   │
│  │ ingest  │ ─────────────► │  PromptBundle (typed Pydantic)   │   │
│  └─────────┘   fingerprint  └──────────────┬───────────────────┘   │
│                                            │                        │
│                             ┌──────────────▼───────────────────┐   │
│                             │            analyze               │   │
│                             │  deterministic passes (always)   │   │
│                             │  + LLM augmentation (optional)   │   │
│                             └──────────────┬───────────────────┘   │
│                                            │ ranked issues          │
│                             ┌──────────────▼───────────────────┐   │
│                             │              fix                 │   │
│                             │  safe-fix gating                 │   │
│                             │  minimal string-level edits      │   │
│                             └──────────────┬───────────────────┘   │
│                                            │ patched PromptBundle   │
│                             ┌──────────────▼───────────────────┐   │
│                             │           evaluate               │   │
│                             │  adversarial scenario set        │   │
│                             │  before/after scoring            │   │
│                             └──────────────┬───────────────────┘   │
│                                            │                        │
│                             ┌──────────────▼───────────────────┐   │
│                             │  artifacts/                      │   │
│                             │  issues · patches · eval report  │   │
│                             └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Installation

Requires **Python 3.9+**.

```bash
# Standard install
pip3 install .

# With dev dependencies (tests, linting)
pip3 install '.[dev]'
```

---

## Configuration

The tool can run fully offline (deterministic mode) or with OpenAI for richer analysis and simulation.

### Option 1 — Environment variable

```bash
export OPENAI_API_KEY=sk-...
```

### Option 2 — `.env` file (recommended for local use)

Create a `.env` file in the repo root or any parent directory:

```env
OPENAI_API_KEY=sk-...

# Optional: override the default runtime model (defaults to gpt-4.1-mini)
PROMPT_TOOL_MODEL=gpt-4.1-mini
```

The CLI uses `python-dotenv` and automatically loads the first `.env` it finds on startup.

### Without an API key

All LLM-backed code paths are disabled. The pipeline still runs using deterministic heuristics and produces the same artifact structure — useful for CI, offline demos, and reproducible runs.

---

## Quick Start

### Run the full pipeline

```bash
prompt-tool run /path/to/prompt.json
```

This chains all four stages and writes everything to `artifacts/`.

### Run stages individually

```bash
# Analyze only — produces issues.json and issues.md
prompt-tool analyze /path/to/prompt.json

# Apply safe fixes — produces patched.json and fixes.md
prompt-tool fix /path/to/prompt.json --apply-safe

# Evaluate original vs patched — produces eval_report.* and summary.json
prompt-tool evaluate /path/to/prompt.json artifacts/patched.json
```

---

## CLI Reference

| Command | Description |
|---|---|
| `prompt-tool run <prompt.json>` | Full pipeline: ingest → analyze → fix → evaluate |
| `prompt-tool analyze <prompt.json>` | Analyze prompt and emit issues only |
| `prompt-tool fix <prompt.json> [--apply-safe]` | Apply safe fixes; surface others as open |
| `prompt-tool evaluate <original.json> <patched.json>` | Run adversarial eval for both prompts |

All commands write to `artifacts/` by default. Use `--output-dir <path>` to override.

---

## Input Format

The CLI expects a single JSON file with the following top-level fields:

```jsonc
{
  "general_prompt": "You are a healthcare front-desk assistant...",
  "tools": [
    {
      "name": "schedule_appointment",
      "description": "...",
      "parameters": { ... }
    }
  ],
  "config": {
    "model": "gpt-4o",
    "temperature": 0.2
  }
}
```


## Pipeline Stages

### 1. Ingest

**Module:** `ingest.py`

Loads the raw JSON file from disk, normalizes field names and shapes into a typed `PromptBundle`, and computes a SHA-256 **fingerprint** so every downstream artifact traces back to a specific input version.

The fingerprint appears in all output files — if you re-run analysis on a modified prompt, artifacts from the two runs are never silently mixed.

### 2. Analyze

**Module:** `analysis.py`

Runs a multi-pass inspection over the prompt and tool schema. Two layers:

**Deterministic passes** (always run, no API key needed):

| Pass | What it checks |
|---|---|
| Workflow adherence | Does the prompt follow the expected call flow? Are required steps present? |
| Tool / schema fit | Does the prompt reference tools correctly? Are parameter types consistent? |
| Patient experience | Are responses appropriately concise? Is the tone consistent? |
| Prompt structure | Are sections well-organised? Are instructions unambiguous? |
| Generalizability | Are domain-specific assumptions hard-coded that could break on new inputs? |

**LLM augmentation** (runs when `OPENAI_API_KEY` is set):

The LLM is given the full prompt and tool schema and asked to propose additional issues with explicit evidence — citations pointing back into the prompt text. These are merged with deterministic findings and de-duplicated before ranking.

Every issue in the output carries:

```jsonc
{
  "id": "waitlist-hallucination",
  "severity": "high",
  "category": "workflow_adherence",
  "evidence": "Line 47: 'I can add you to the waitlist' — no waitlist tool exists",
  "failure_mode": "Agent promises behavior it cannot fulfil",
  "suggested_fix_op": "replace",
  "safe_to_auto_apply": true
}
```

### 3. Fix

**Module:** `fixes.py`

Takes the ranked issue list from analysis and applies minimal, auditable edits to `general_prompt`. Three edit operations:

| Operation | Effect |
|---|---|
| `replace` | Swap a specific text span for corrected text |
| `insert_after` | Inject new text immediately after a matched anchor string |
| `remove` | Delete a specific span entirely |

**Safe-fix gating** is the core safety mechanism. Issues are only auto-applied if they are:

1. Tagged `safe_to_auto_apply: true` in analysis output, **and**
2. Solvable purely at the prompt level (no system/tool changes required)

Issues that reflect a system limitation — for example, a tool that requires an ID with no lookup mechanism — are surfaced in `fixes.md` as open items but left untouched. Patching the prompt to work around a broken tool would introduce misleading behavior, not fix it.

### 4. Evaluate

**Modules:** `evaluate.py`, `scenarios.py`

Runs both the original and patched prompts through a set of **adversarial caller scenarios** and produces before/after scores.

**Scenario categories:**

| Category | Example scenario |
|---|---|
| Waitlist hallucination | Caller asks to be added to a waitlist — agent must not promise it |
| Unknown ordering provider | Caller gives an unrecognised provider name — agent must clarify, not guess |
| Visit type normalization | Caller says "follow-up" — agent must map to `follow_up` enum correctly |
| Conciseness | Simple yes/no question — agent must not over-explain |

Each scenario has explicit **pass/fail checks**, making scores objective and reproducible.

 The evaluator simulates full multi-turn caller/assistant transcripts via OpenAI, then applies rule-based checks and an optional LLM judge to produce natural-language rationales.


---

## Output Artifacts

All artifacts are written to `artifacts/` (or `--output-dir`):

| File | Description |
|---|---|
| `issues.json` | Structured issue list with severity, evidence, and fix operations |
| `issues.md` | Human-readable issue report for stakeholder review |
| `patched.json` | Full `PromptBundle` with safe fixes applied — directly diffable against input |
| `fixes.md` | Summary of every applied fix and every skipped fix, with reasons |
| `eval_report.json` | Per-scenario scores, transcripts, and pass/fail evidence |
| `eval_report.md` | Human-readable evaluation report with before/after comparison |
| `summary.json` | Top-level summary including aggregate before/after delta |

---

## Architecture

### Module Map

```
prompt-agent/
├── prompt_tool/
│   ├── cli.py          # Typer CLI — commands, .env loading, output formatting
│   ├── models.py       # Pydantic contracts — single source of truth for all data shapes
│   ├── ingest.py       # Load, normalize, fingerprint → PromptBundle
│   ├── analysis.py     # Multi-pass issue detection (deterministic + LLM)
│   ├── fixes.py        # Safe-fix gating + string-level patch application
│   ├── scenarios.py    # Adversarial scenario definitions
│   ├── evaluate.py     # Simulation, scoring, and report generation
│   └── llm.py          # OpenAI client wrapper (only file that calls the API)
├── tests/              # unittest suite — one file per module
├── artifacts/          # Generated outputs (gitignored)
└── prompt.json         # Reference input — healthcare front-desk spec
```

### Data Flow

Every piece of data that crosses a module boundary does so as a typed Pydantic model defined in `models.py`. There are no ad-hoc dicts passed between stages.

```
prompt.json  ──►  PromptBundle  ──►  IssueList  ──►  PatchedBundle  ──►  EvalReport
   (disk)       (ingest.py)       (analysis.py)    (fixes.py)         (evaluate.py)
```

This means:

- `ingest` is the only module that knows about the raw JSON file format
- `analysis`, `fixes`, and `evaluate` are loosely coupled — swapping one does not break the others
- `llm.py` is the only module that calls OpenAI — the entire rest of the system runs offline

### Key Design Decisions

#### Hybrid analyzer instead of LLM-only analysis

Pure LLM analysis would be clever but hard to validate. Healthcare workflows require grounded, inspectable findings — not suggestions that can't be traced to a specific text span.

High-confidence issues (unsupported waitlist behavior, missing ID resolution, wrong visit-type mapping) are caught deterministically with no API cost. The LLM layer adds coverage for subtle issues the heuristics miss, but it is augmentation, not the source of truth.

#### Minimal patching instead of full prompt rewrite

Rewriting an 8,000–12,000 token prompt is risky and very hard to review. The fix stage instead operates as a diff engine: small `replace`, `insert_after`, and `remove` operations on specific text spans. Existing working behaviors are untouched unless a targeted issue demands change. Reviewers can open `patched.json` and immediately see what changed and why.

#### Safe-fix gating

Some issues are fixable at the prompt level. Others reflect system or tool limitations that cannot be resolved by editing text. Auto-applying a prompt patch to work around a tool that lacks an ID lookup doesn't solve anything — it creates a prompt that promises behavior the system can't deliver. Safe-fix gating separates these categories explicitly.

#### Explicit adversarial evaluation

"The new prompt feels better" is not evidence. The evaluator targets specific known failure modes with explicit pass/fail checks. Before/after scores are meaningful because they measure the same scenarios with the same criteria — not impressionistic LLM scoring.

#### Batched LLM calls with a cheaper default model

Evaluating each scenario independently resends the full system prompt on every call. Token-heavy evaluation is slow, expensive, and hits rate limits. Scenarios are batched to reduce duplicated context. The default model is `gpt-4.1-mini` (configurable via `PROMPT_TOOL_MODEL`), which makes LLM-backed runs significantly more affordable without sacrificing the quality needed for evaluation.

---

## How LLMs Are Used

### When `OPENAI_API_KEY` is set

| Stage | LLM role |
|---|---|
| Analyze | Propose additional grounded issues with evidence citations from the prompt |
| Fix | For complex issue types without a deterministic patch, propose a candidate edit for human review |
| Evaluate | Simulate realistic multi-turn caller/assistant transcripts per scenario |
| Evaluate | Sanity-check deterministic scores and produce natural-language rationales |

### When `OPENAI_API_KEY` is not set

All LLM paths are disabled. The pipeline falls back to deterministic checks and produces the same artifact structure. The tool is fully usable offline — useful for CI pipelines, reproducible runs, and environments where API access is restricted.

---

## Testing

```bash
python3 -m unittest discover -s tests -v
```

The test suite covers:

- Prompt parsing and `PromptBundle` validation
- Deterministic issue detection across all analysis passes
- Fix application: `replace`, `insert_after`, `remove` operations
- Safe-fix gating logic
- Evaluation scoring and report generation
- LLM output normalization into internal Pydantic models

> **Note:** `pytest` was the original test runner but hit a segfault during collection in this environment. The suite uses `unittest` for stability. All test logic is identical.

---

## Current Limitations

### Tool/runtime contract clarity

Some issues — particularly around strict ID requirements with no lookup mechanism — cannot be fully resolved at the prompt level. The tool currently surfaces these as open issues but has no way to classify them as "prompt defects" vs "system defects" with high confidence. A more explicit tool-capability layer would sharpen this distinction.

### String-based patching

Patches operate on raw text spans. There is no AST- or schema-aware editing, so concurrent patches targeting overlapping spans can conflict. Patch confidence is not yet modelled — a `replace` that matches in two places will be flagged as ambiguous but not automatically resolved.

### Evaluation realism

The current evaluator focuses on single-turn and short multi-turn transcripts. It does not simulate tool call results, long-running multi-session flows, or caller interruptions. Scenarios where the agent's behavior depends on what a tool returns are tested with mocked responses.


# e2e-timewalker

> English edition · [简体中文](./README.zh.md)

**e2e-timewalker** is the end-to-end testing toolkit for the Kimi CLI monorepo. It records every terminal frame of a scenario, replays the interaction timeline, and highlights meaningful differences against a trusted baseline. The goal is to make "non-deterministic" CLI workflows observable, reviewable, and auditable.

Think of it as a time-travel recorder for agent sessions: you can jump back to any command, inspect colours, cursor moves, or tool invocations, and ship actionable reports to reviewers or CI.

---

## Key capabilities

- **Scenario runner** – executes scripted CLI sessions inside a PTY sandbox with deterministic prompts and helper commands.
- **Timeline capture** – stores raw output streams, structured events, user inputs, and environment metadata.
- **State replay** – reconstructs terminal screens as HTML/PNG/text keyframes for side-by-side inspection.
- **Diff & insights** – compares outputs with a stable baseline, emits rule-based and LLM-assisted warnings.
- **Automation friendly** – exposes Make targets, CLI entry points, and CI recipes for easy adoption.

---

## Architecture

```
┌──────────────────────────────┐
│        Scenario Runner       │
│  - PTY management            │
│  - JSON DSL executor         │
│  - Env injection             │
└──────────────┬───────────────┘
               │ timeline data
┌──────────────▼───────────────┐
│        Data Recorder         │
│  - Raw stream                │
│  - Structured log            │
│  - Metadata bundle           │
└──────────────┬───────────────┘
               │ artefacts
┌──────────────▼───────────────┐
│   Replay & Inspection stack  │
│  - HTML/PNG/Text keyframes   │
│  - Baseline diff             │
│  - Warnings & annotations    │
└──────────────┬───────────────┘
               │ report model
┌──────────────▼───────────────┐
│  Report & Workflow adapter   │
│  - Markdown/HTML output      │
│  - Make/CLI integration      │
│  - CI hooks & reviewers      │
└──────────────────────────────┘
```

---

## Workflow summary

1. **Prepare** – choose or author a JSON scenario file describing the session.
2. **Run** – execute the scenario through `make e2e-run` (or the Python entry point) to produce a result bundle.
3. **Replay** – feed the bundle to `make e2e-report` to rebuild screens, diff against baselines, and generate a report.
4. **Review** – inspect keyframes, warnings, and logs locally or via CI artefacts.
5. **Iterate** – update baselines, ignore rules, or scenario steps as legitimate changes land.

---

## JSON scenario DSL (draft)

```json
{
  "name": "echo_conversation",
  "description": "Fire a prompt through the echo provider",
  "vars": {
    "workspace": "~/demo"
  },
  "steps": [
    { "type": "command", "run": "cd {{ workspace }}" },
    { "type": "command", "run": "kimi --provider echo --message 'hello'" },
    {
      "type": "wait",
      "expect": { "contains": "hello" },
      "timeout": 5
    },
    { "type": "snapshot", "label": "after_echo" }
  ]
}
```

Features in scope:
- **Command steps** – send arbitrary shell input to the PTY.
- **Wait steps** – poll the output for patterns or custom predicates with timeouts.
- **Snapshot steps** – mark points of interest for replay and reporting.
- **Variables & templates** – reuse directories, flags, or secrets safely.
- **Schema validation** – JSON Schema ensures scenarios are well-formed before execution.

---

## CLI & Make targets (planned)

| Target | Description |
|--------|-------------|
| `make e2e-run` | Run a JSON scenario (`SCENARIO=...`) and emit a result bundle (`OUTDIR=...`). |
| `make e2e-report` | Analyse a result bundle (`RESULT=...`), regenerate keyframes, produce Markdown/HTML reports. |
| `make e2e-all` | Convenience wrapper that runs `e2e-run` followed by `e2e-report`. |

Python entry points mirror these targets (e.g. `uv run python -m e2e_timewalker.run` and `...report`).

---

## Repository layout (proposed)

```
kimi-cli/e2e-timewalker/
├── README.md / README.zh.md
├── Makefile.inc               # make targets imported by the root Makefile
├── timewalker/
│   ├── runner.py              # PTY orchestration & DSL engine
│   ├── recorder.py            # raw/structured capture
│   ├── replayer.py            # keyframe generation utilities
│   ├── inspector.py           # diff, rules, LLM hooks
│   ├── reporter.py            # report rendering helpers
│   └── dsl/
│       ├── schema.json        # JSON schema for scenarios
│       └── parser.py          # validation & templating
├── scenarios/                 # sample & real scenarios
├── baselines/                 # reference keyframes (git tracked)
├── outputs/                   # generated artefacts (gitignored)
└── workflows/github-example.yml (optional)
```

---

## Integration patterns

- **Local iteration** – edit a scenario, run `make e2e-run`, view raw artefacts, tweak, then `make e2e-report`.
- **Baseline updates** – after approving changes, refresh the matching assets under `baselines/` via helper commands.
- **CI checks** – add a job that calls `make e2e-all`; upload reports and reference them in PR comments.
- **Reviewer workflow** – consume the Markdown report, acknowledge warnings, adjust ignore lists, or trigger re-runs.

---

## Roadmap highlights

- Expand DSL (loops, branching, parallel regions, reusable macros).
- Build a lightweight web viewer for browsing timelines and diffs.
- Enhance rule engine, integrate richer LLM prompts for summarising visual changes.
- Harden cross-platform support (macOS/Linux containers/WSL).

---

## Contributing

1. Read both README files to familiarise yourself with goals and structure.
2. Pick a component (runner, recorder, replayer, inspector, reporter, DSL) and propose implementation details.
3. Use the sample scenario as a starting point when testing the pipeline.
4. Keep documentation and JSON Schema in sync as the DSL surface evolves.

Feedback is welcome via issues or pull requests. Happy time travelling!

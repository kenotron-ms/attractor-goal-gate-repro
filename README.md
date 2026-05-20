# loop-pipeline: goal_gate FAIL silently becomes success

Minimal reproducer for a bug in `amplifier-bundle-attractor` (`loop-pipeline` backend):
a `goal_gate=true` node that explicitly returns `{"status":"fail"}` is silently
treated as success when a provider exists on the outer session.

## One-liner

```bash
ANTHROPIC_API_KEY=sk-... uv run python main.py
```

Look for this mismatch in the output:

```
[attractor-agent-anthropic output]
{"status": "fail", "failure_reason": "intentional: this gate always fails"}

[PIPELINE] ✓ gate: success          ← bug: should be ✗ gate: fail
```

The gate says fail. The pipeline says success.

## Prerequisites

[uv](https://docs.astral.sh/uv/) — that's it. `uv run` reads `pyproject.toml`,
creates an isolated venv, installs `amplifier`, and runs the script in one step.

## Files

| File | Purpose |
|------|---------|
| `repro.dot` | Minimal pipeline — one `goal_gate=true` node that always returns `{"status":"fail"}` |
| `repro.bundle.md` | Includes `amplifier-bundle-attractor@main`, which places `provider-anthropic` on the outer session — the bug trigger |
| `main.py` | Runs the pipeline via the Amplifier Python API; routes `[PIPELINE]` logs to stdout |

## What's happening

`AmplifierBackend.execute()` in the `loop-pipeline` module contains a
spawn-to-tool-loop fallback that fires on **any** FAIL outcome:

```python
if outcome.status == StageStatus.FAIL and self._provider is not None:
    outcome = await self._run_with_tool_loop(...)   # re-runs WITHOUT thread history
```

This was designed for spawn infrastructure failures (e.g. `session.spawn` threw an
exception). It also fires when a `goal_gate=true` node correctly reports `{"status":"fail"}`.

The re-run (`_run_with_tool_loop`) has no access to the child session's thread history.
The LLM has nothing meaningful to evaluate, defaults to success, and the gate is bypassed
silently — no warning is emitted.

**Trigger conditions:**
- `goal_gate=true` on a pipeline node
- A provider present on the outer `loop-pipeline` session (inherited from
  `amplifier-bundle-attractor@main` via `repro.bundle.md`)

## Pipeline

```
start → gate [goal_gate=true, always outputs {"status":"fail"}]
              └─ outcome=success → reached_done   ← BUG: this executes
              └─ (no fail edge)                   ← correct: pipeline should halt here
```

## Shortcoming

The fallback predicate `outcome.status == StageStatus.FAIL` is too broad. It should
distinguish spawn infrastructure failures (where a retry makes sense) from intentional
node-reported failures (where the verdict must propagate unchanged). Additionally,
no log line is emitted when the fallback converts an outcome, making the bug invisible
without knowing to look for it.

## Filed

[microsoft-amplifier/amplifier-support](https://github.com/microsoft-amplifier/amplifier-support)

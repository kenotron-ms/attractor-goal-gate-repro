# loop-pipeline: goal_gate FAIL silently bypasses gate

Minimal reproducer for a bug in `amplifier-bundle-attractor` (`loop-pipeline` backend):
a `goal_gate=true` node that explicitly returns `{"status":"fail"}` is silently
bypassed — downstream nodes still execute.

## One-liner

```bash
uv run python main.py
```

Look for this mismatch in the output:

```
[gate-agent output]
{"status": "fail", "failure_reason": "intentional: this gate always fails"}

[PIPELINE] ✓ gate: success          ← bug variant A: gate marked success despite fail
```

or

```
[gate-agent output]
{"status": "fail", "failure_reason": "intentional: this gate always fails"}

[PIPELINE] ✗ gate: fail
[PIPELINE] -> edge: gate --[]--> reached_done   ← bug variant B: fail routes to success edge
[PIPELINE] Complete: fail                        ← only caught by goal_gate safety net
```

Either way: the gate said fail. Downstream nodes still executed.

## Prerequisites

[uv](https://docs.astral.sh/uv/) — that's it. `uv run` reads `pyproject.toml`,
creates an isolated venv, and installs all dependencies in one step.

```bash
export ANTHROPIC_API_KEY=sk-...
```

## Files

| File | Purpose |
|------|---------|
| `repro.dot` | Minimal pipeline — one `goal_gate=true` node that always returns `{"status":"fail"}` |
| `repro.bundle.md` | Self-contained bundle: `provider-anthropic` on the outer session (the bug trigger), `loop-pipeline` orchestrator, inline `gate-agent` definition |
| `main.py` | Runs the pipeline via the Amplifier Python API |
| `pyproject.toml` | Declares all attractor module deps so `uv run` installs them |

## What's happening

`AmplifierBackend.execute()` in the `loop-pipeline` module contains a
spawn-to-tool-loop fallback that fires on **any** FAIL outcome:

```python
if outcome.status == StageStatus.FAIL and self._provider is not None:
    outcome = await self._run_with_tool_loop(...)   # re-runs WITHOUT child session history
```

This was designed for spawn infrastructure failures (e.g. `session.spawn` threw an
exception). It also fires when a `goal_gate=true` node correctly reports `{"status":"fail"}`.

The re-run (`_run_with_tool_loop`) has no access to the child session's conversation
history. Without context, the LLM has nothing meaningful to evaluate and defaults
to a success-shaped response. `_parse_outcome` then returns `StageStatus.SUCCESS` —
either because the response parsed as success, or because any unrecognized plain-text
response maps to SUCCESS (spec section 4.5).

A second path also exists: when the edge selector has only one outgoing edge and no
condition matches, it may select the edge regardless. `reached_done` then executes
even when the gate reports `fail`.

**Trigger conditions:**
- `goal_gate=true` on a pipeline node
- A provider present on the outer `loop-pipeline` session (`repro.bundle.md` supplies one)

## Pipeline

```
start → gate [goal_gate=true, always outputs {"status":"fail"}]
              └─ outcome=success → reached_done   ← BUG: this executes anyway
              └─ (no fail edge)                   ← correct: pipeline should halt here
```

## Shortcoming

1. The fallback predicate `outcome.status == StageStatus.FAIL` is too broad — it should
   distinguish spawn infrastructure failures (where a retry makes sense) from intentional
   node-reported failures (where the verdict must propagate unchanged).

2. No log line is emitted when the fallback converts an outcome, making the bug invisible
   without knowing to look for it.

3. `_parse_outcome` maps plain-text responses to `StageStatus.SUCCESS` per spec section 4.5.
   This means any fallback that generates a prose response will silently pass the gate.

## Filed

[microsoft-amplifier/amplifier-support](https://github.com/microsoft-amplifier/amplifier-support)

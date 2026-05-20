---
bundle:
  name: goal-gate-fail-repro
  version: 1.0.0
  description: >
    Trigger bundle for the loop-pipeline goal_gate FAIL→success bug.

    Including amplifier-bundle-attractor@main places provider-anthropic on the
    outer loop-pipeline session. That makes AmplifierBackend.self._provider != None,
    which triggers the spawn→tool-loop fallback on ANY FAIL outcome — including
    intentional goal_gate failures from quality_eval nodes.

# The upstream bundle contributes:
#   - provider-anthropic on the outer session  ← bug trigger
#   - loop-pipeline orchestrator
#   - attractor-agent-anthropic child profile (used by the gate node)
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-attractor@main
---

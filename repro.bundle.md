---
bundle:
  name: goal-gate-fail-repro
  version: 1.0.0
  description: >
    Self-contained trigger bundle for the loop-pipeline goal_gate FAIL→success bug.

    The outer session carries provider-anthropic, which makes
    AmplifierBackend.self._provider != None. When a goal_gate node correctly
    returns {"status":"fail"}, that triggers the spawn→tool-loop fallback,
    which re-runs the node without child session history, returns success, and
    silently bypasses the gate.

# Outer session: loop-pipeline with provider-anthropic.
# Provider on outer session is the trigger condition for the bug.
providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
    config:
      default_model: claude-haiku-4-5-20251001

session:
  orchestrator:
    module: loop-pipeline
    source: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=modules/loop-pipeline
    config:
      profiles:
        anthropic: gate-agent   # maps default llm_provider="anthropic" to our agent
  context:
    module: context-simple
    source: git+https://github.com/microsoft/amplifier-module-context-simple@main

hooks:
  - module: hooks-pipeline-progress
    source: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=modules/hooks-pipeline-progress

# gate-agent: runs loop-agent with a provider, so it can call the LLM.
# The gate prompt tells it to ALWAYS return {"status":"fail"}.
agents:
  gate-agent:
    session:
      orchestrator:
        module: loop-agent
        source: git+https://github.com/microsoft/amplifier-bundle-attractor@main#subdirectory=modules/loop-agent
        config:
          max_tool_rounds_per_input: 3
      context:
        module: context-simple
        source: git+https://github.com/microsoft/amplifier-module-context-simple@main
    providers:
      - module: provider-anthropic
        source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
        config:
          default_model: claude-haiku-4-5-20251001
---

#!/usr/bin/env python3
"""
Reproducer: loop-pipeline silently converts goal_gate FAIL to success.

The gate node in repro.dot always outputs {"status":"fail"}.

Expected:  [PIPELINE] ✗ gate: fail
Actual:    [PIPELINE] ✓ gate: success   ← bug

Run:
    uv run python main.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

# Show only [PIPELINE] lines — suppress all other Amplifier internals.
logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(message)s")

class _PipelineOnly(logging.Handler):
    """Emit only lines containing [PIPELINE] so the mismatch stands out."""
    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "[PIPELINE]" in msg:
            print(msg, flush=True)

_h = _PipelineOnly()
_h.setFormatter(logging.Formatter("%(message)s"))
_prog_log = logging.getLogger("amplifier_module_hooks_pipeline_progress")
_prog_log.handlers = [_h]
_prog_log.setLevel(logging.DEBUG)
_prog_log.propagate = False


def _register_spawn(session: Any, prepared: Any) -> None:
    """Wire session.spawn so AmplifierBackend is selected by loop-pipeline."""
    from amplifier_foundation import Bundle
    from amplifier_foundation.bundle import PreparedBundle

    assert isinstance(prepared, PreparedBundle)

    async def spawn_capability(
        agent_name: str,
        instruction: str,
        parent_session: Any,
        agent_configs: dict[str, dict[str, Any]],
        sub_session_id: str | None = None,
        orchestrator_config: dict[str, Any] | None = None,
        parent_messages: list[dict[str, Any]] | None = None,
        provider_preferences: list | None = None,
        self_delegation_depth: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Look up agent config: coordinator's agent_configs first, then bundle agents.
        if agent_name in agent_configs:
            config = agent_configs[agent_name]
        elif agent_name in prepared.bundle.agents:
            config = prepared.bundle.agents[agent_name]
        else:
            available = list(agent_configs) + list(prepared.bundle.agents)
            raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

        child_bundle = Bundle(
            name=agent_name,
            version="1.0.0",
            session=config.get("session", {}),
            providers=config.get("providers", []),
            tools=config.get("tools", []),
            hooks=config.get("hooks", []),
            instruction=config.get("instruction")
            or (config.get("system") or {}).get("instruction"),
        )

        result = await prepared.spawn(
            child_bundle=child_bundle,
            instruction=instruction,
            session_id=sub_session_id,
            parent_session=parent_session,
            orchestrator_config=orchestrator_config,
            parent_messages=parent_messages,
            provider_preferences=provider_preferences,
            self_delegation_depth=self_delegation_depth,
        )

        output = (result or {}).get("output") or (result or {}).get("response") or ""
        if output:
            print(f"\n[{agent_name} output]\n{output}", flush=True)

        return result

    session.coordinator.register_capability("session.spawn", spawn_capability)


async def run() -> int:
    from amplifier_foundation import Bundle, load_bundle

    dot_source = Path("repro.dot").read_text()
    logs_root = tempfile.mkdtemp(prefix="attractor-repro-")

    # repro.bundle.md defines:
    #   - provider-anthropic on the outer session (the bug trigger condition)
    #   - loop-pipeline as orchestrator with profiles: {anthropic: gate-agent}
    #   - gate-agent: loop-agent + provider-anthropic (inline, no bundle refs)
    bundle = await load_bundle(str(Path("repro.bundle.md").resolve()))
    overlay = Bundle(
        name="repro-overlay",
        version="1.0.0",
        session={
            "orchestrator": {
                "module": "loop-pipeline",   # must be explicit in overlay
                "config": {
                    "dot_source": dot_source,
                    "logs_root": logs_root,
                },
            }
        },
    )
    composed = bundle.compose(overlay)
    prepared = await composed.prepare()

    # Use prepared.create_session() — not the CLI's create_initialized_session(),
    # which reads existing session state from the parent process.
    session = await prepared.create_session(session_cwd=Path.cwd())
    _register_spawn(session, prepared)

    async with session:
        await session.execute("Run the pipeline")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))

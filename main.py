#!/usr/bin/env python3
"""
Reproducer: loop-pipeline silently converts goal_gate FAIL to success.

The gate node in repro.dot is instructed to always return {"status": "fail"}.

Expected:  [PIPELINE] ✗ gate: fail
Actual:    [PIPELINE] ✓ gate: success   ← bug

Prerequisites:
    pip install amplifier   # or: uv tool install amplifier
    export ANTHROPIC_API_KEY=sk-...

Run:
    python main.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Route [PIPELINE] progress lines to stdout so the mismatch is immediately
# visible. Without this the hook logs go to the Amplifier log file only.
# ---------------------------------------------------------------------------
def _configure_pipeline_logger() -> None:
    log = logging.getLogger("amplifier_module_hooks_pipeline_progress")
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(h)
        log.setLevel(logging.DEBUG)
        log.propagate = False


# ---------------------------------------------------------------------------
# Wire session.spawn so loop-pipeline selects AmplifierBackend.
# Without this the engine falls back to DirectProviderBackend and the bug
# path (spawn → _run_with_tool_loop) is never reached.
# ---------------------------------------------------------------------------
def _register_spawn(session: object, prepared: object) -> None:
    from amplifier_foundation import Bundle

    async def spawn_capability(
        agent_name: str,
        instruction: str,
        parent_session: object,
        agent_configs: dict,
        sub_session_id: str | None = None,
        orchestrator_config: dict | None = None,
        parent_messages: list | None = None,
        provider_preferences: list | None = None,
        self_delegation_depth: int = 0,
        **kwargs: object,
    ) -> dict:
        config: dict = {}
        if agent_name in agent_configs:
            config = agent_configs[agent_name]
        elif hasattr(prepared, "bundle"):
            agents = prepared.bundle.agents or {}
            if agent_name in agents:
                config = agents[agent_name]

        child_bundle = Bundle(
            name=agent_name or "pipeline-node",
            version="1.0.0",
            session=config.get("session", {}),
            providers=config.get("providers", []),
            tools=config.get("tools", []),
            hooks=config.get("hooks", []),
            instruction=(
                config.get("instruction")
                or (config.get("system") or {}).get("instruction")
            ),
        )

        result = await prepared.spawn(
            child_bundle=child_bundle,
            instruction=instruction,
            compose=False,
            session_id=sub_session_id,
            parent_session=parent_session,
            orchestrator_config=orchestrator_config,
            parent_messages=parent_messages,
            provider_preferences=provider_preferences,
            self_delegation_depth=self_delegation_depth,
        )

        result_dict = result or {}
        output = result_dict.get("output") or result_dict.get("response") or ""
        if output:
            print(f"\n[{agent_name} output]\n{output}", flush=True)

        return result

    session.coordinator.register_capability("session.spawn", spawn_capability)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run() -> int:
    from amplifier_app_cli.console import console
    from amplifier_app_cli.session_runner import SessionConfig, create_initialized_session
    from amplifier_foundation import Bundle, load_bundle

    _configure_pipeline_logger()

    dot_source = Path("repro.dot").read_text()
    logs_root = tempfile.mkdtemp(prefix="attractor-repro-")

    # Load the trigger bundle (includes amplifier-bundle-attractor@main which places
    # provider-anthropic on the outer session — the bug condition).
    base = await load_bundle(str(Path("repro.bundle.md").resolve()))

    # Overlay injects the DOT source at runtime so the bundle file stays clean.
    overlay = Bundle(
        name="repro-overlay",
        version="1.0.0",
        session={
            "orchestrator": {
                "config": {
                    "dot_source": dot_source,
                    "logs_root": logs_root,
                },
            }
        },
    )
    composed = base.compose(overlay)
    prepared = await composed.prepare()

    sc = SessionConfig(
        config={},
        search_paths=[Path(".")],
        verbose=False,
        prepared_bundle=prepared,
        bundle_name="repro.bundle.md",
    )
    initialized = await create_initialized_session(sc, console)
    _register_spawn(initialized.session, prepared)

    try:
        await initialized.session.execute("test")
    finally:
        await initialized.cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))

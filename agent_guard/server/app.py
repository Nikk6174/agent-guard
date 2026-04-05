# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
FastAPI application for the AgentGuard Permission Governance Simulator.

This module creates an HTTP server that exposes the AgentGuardEnvironment
over HTTP and WebSocket endpoints, compatible with EnvClient.

Endpoints:
    - POST /reset: Reset the environment
    - POST /step: Execute an action
    - GET /state: Get current environment state
    - GET /schema: Get action/observation schemas
    - WS /ws: WebSocket endpoint for persistent sessions

Usage:
    # Development (with auto-reload):
    uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

    # Production:
    uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 2
"""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with '\n    uv sync\n'"
    ) from e

try:
    from ..models import AgentGuardAction, AgentGuardObservation
    from .agent_guard_environment import AgentGuardEnvironment
except (ImportError, ModuleNotFoundError):
    from models import AgentGuardAction, AgentGuardObservation
    from server.agent_guard_environment import AgentGuardEnvironment


# Create the app with concurrent session support
app = create_app(
    AgentGuardEnvironment,
    AgentGuardAction,
    AgentGuardObservation,
    env_name="agent_guard",
    max_concurrent_envs=4,
)


# ── Root & Health endpoints ─────────────────────────────────────────────

from fastapi.responses import JSONResponse


@app.get("/")
async def root():
    """Root endpoint — confirms the environment is live."""
    return JSONResponse({
        "name": "AgentGuard V3",
        "description": "Adversarial Permission Governance Simulator",
        "version": "3.0.0",
        "status": "running",
        "endpoints": {
            "reset": "POST /reset",
            "step": "POST /step",
            "state": "GET /state",
            "health": "GET /health",
            "websocket": "WS /ws",
        },
        "scenarios": 13,
        "reward_dimensions": ["decision_correctness", "investigation_quality",
                              "reasoning_quality", "urgency_awareness"],
    })


@app.get("/health")
async def health():
    """Health check endpoint for Docker/HF Spaces."""
    return JSONResponse({"status": "healthy"})


def main(host: str = "0.0.0.0", port: int = 8000):
    """
    Entry point for direct execution via uv run or python -m.

    Args:
        host: Host address to bind to (default: "0.0.0.0")
        port: Port number to listen on (default: 8000)
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

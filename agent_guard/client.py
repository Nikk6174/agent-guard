# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""AgentGuard Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

try:
    from .models import (
        ActiveIncident,
        AgentGuardAction,
        AgentGuardObservation,
        AgentHistoryEntry,
        IAMPolicyContext,
        IncomingRequest,
        RewardBreakdown,
        ResourceType,
        TaskDifficulty,
        UrgencyLevel,
    )
except (ImportError, ModuleNotFoundError):
    from models import (
        ActiveIncident,
        AgentGuardAction,
        AgentGuardObservation,
        AgentHistoryEntry,
        IAMPolicyContext,
        IncomingRequest,
        RewardBreakdown,
        ResourceType,
        TaskDifficulty,
        UrgencyLevel,
    )


class AgentGuardEnv(
    EnvClient[AgentGuardAction, AgentGuardObservation, State]
):
    """
    Client for the AgentGuard Permission Governance Simulator.

    This client maintains a persistent WebSocket connection to the environment
    server, enabling efficient multi-step interactions with lower latency.

    Example:
        >>> with AgentGuardEnv(base_url="http://localhost:8000") as client:
        ...     result = client.reset()
        ...     obs = result.observation
        ...     print(obs.task_id, obs.task_difficulty)
        ...
        ...     action = AgentGuardAction(decision=ActionType.DENY, reasoning="No ticket")
        ...     result = client.step(action)
        ...     print(result.reward, result.done)

    Example with Docker:
        >>> client = AgentGuardEnv.from_docker_image("agent_guard-env:latest")
        >>> try:
        ...     result = client.reset()
        ...     result = client.step(AgentGuardAction(decision=ActionType.ESCALATE))
        ... finally:
        ...     client.close()
    """

    def _step_payload(self, action: AgentGuardAction) -> Dict:
        """
        Convert AgentGuardAction to JSON payload for step message.

        Args:
            action: AgentGuardAction instance with decision and reasoning

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        return {
            "decision": action.decision.value,
            "reasoning": action.reasoning,
        }

    def _parse_result(self, payload: Dict) -> StepResult[AgentGuardObservation]:
        """
        Parse server response into StepResult[AgentGuardObservation].

        Reconstructs all nested Pydantic models from the JSON payload.

        Args:
            payload: JSON response data from server

        Returns:
            StepResult with AgentGuardObservation
        """
        obs_data = payload.get("observation", {})

        # Reconstruct nested models from JSON
        incoming_request = None
        if obs_data.get("incoming_request"):
            req = obs_data["incoming_request"]
            incoming_request = IncomingRequest(
                agent_id=req["agent_id"],
                agent_name=req["agent_name"],
                intended_action=req["intended_action"],
                target_resource=req["target_resource"],
                resource_type=ResourceType(req["resource_type"]),
                urgency=UrgencyLevel(req["urgency"]),
                justification=req["justification"],
                associated_ticket=req.get("associated_ticket"),
            )

        agent_history = [
            AgentHistoryEntry(
                action=entry["action"],
                target=entry["target"],
                timestamp=entry["timestamp"],
                outcome=entry["outcome"],
            )
            for entry in obs_data.get("agent_history", [])
        ]

        iam_policy = None
        if obs_data.get("iam_policy_context"):
            pol = obs_data["iam_policy_context"]
            iam_policy = IAMPolicyContext(
                policy_id=pol["policy_id"],
                policy_name=pol["policy_name"],
                policy_text=pol["policy_text"],
                applicable_roles=pol.get("applicable_roles", []),
                exceptions=pol.get("exceptions", []),
            )

        active_incidents = [
            ActiveIncident(
                incident_id=inc["incident_id"],
                severity=inc["severity"],
                title=inc["title"],
                affected_services=inc.get("affected_services", []),
            )
            for inc in obs_data.get("active_incidents", [])
        ]

        # Parse task_difficulty safely
        task_difficulty = None
        if obs_data.get("task_difficulty"):
            try:
                task_difficulty = TaskDifficulty(obs_data["task_difficulty"])
            except ValueError:
                task_difficulty = None

        # Parse reward breakdown (only present on terminal decisions)
        reward_breakdown = None
        if obs_data.get("reward_breakdown"):
            rb = obs_data["reward_breakdown"]
            reward_breakdown = RewardBreakdown(
                decision_correctness=rb.get("decision_correctness", 0.0),
                investigation_quality=rb.get("investigation_quality", 0.0),
                reasoning_quality=rb.get("reasoning_quality", 0.0),
                urgency_awareness=rb.get("urgency_awareness", 0.0),
                total=rb.get("total", 0.0),
                explanation=rb.get("explanation", ""),
            )

        observation = AgentGuardObservation(
            incoming_request=incoming_request,
            agent_history=agent_history,
            iam_policy_context=iam_policy,
            active_incidents=active_incidents,
            task_id=obs_data.get("task_id", ""),
            task_difficulty=task_difficulty,
            scenario_description=obs_data.get("scenario_description", ""),
            step_number=obs_data.get("step_number", 0),
            total_steps=obs_data.get("total_steps", 1),
            feedback=obs_data.get("feedback", ""),
            investigation_depth=obs_data.get("investigation_depth", 0),
            available_info=obs_data.get("available_info", []),
            reward_breakdown=reward_breakdown,
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        """
        Parse server response into State object.

        Args:
            payload: JSON response from state request

        Returns:
            State object with episode_id and step_count
        """
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )

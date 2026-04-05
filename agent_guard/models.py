# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for the AgentGuard Permission Governance Simulator.

Defines the typed Pydantic schemas for the observation space (what the
Safety Reviewer sees), the action space (decisions it can make), and
supporting sub-models for a realistic DevOps/IAM environment.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import BaseModel, Field


# ─── Enumerations ──────────────────────────────────────────────────────


class ActionType(str, Enum):
    """Discrete action space for the Safety Reviewer."""

    APPROVE = "APPROVE"
    DENY = "DENY"
    ESCALATE = "ESCALATE"
    REQUEST_INFO = "REQUEST_INFO"


class UrgencyLevel(str, Enum):
    """Urgency classification of the incoming request."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ResourceType(str, Enum):
    """Categories of target resources in the simulated infrastructure."""

    DATABASE = "DATABASE"
    S3_BUCKET = "S3_BUCKET"
    API_ENDPOINT = "API_ENDPOINT"
    CODE_REPOSITORY = "CODE_REPOSITORY"
    LOG_SYSTEM = "LOG_SYSTEM"
    CI_CD_PIPELINE = "CI_CD_PIPELINE"
    INTERNAL_FORUM = "INTERNAL_FORUM"
    EXTERNAL_VENDOR_API = "EXTERNAL_VENDOR_API"
    FIREWALL = "FIREWALL"
    PACKAGE_REGISTRY = "PACKAGE_REGISTRY"


class TaskDifficulty(str, Enum):
    """Task difficulty tiers."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class AgentIntent(str, Enum):
    """Hidden intent classification of the requesting agent (grading metadata only)."""

    HONEST = "honest"
    DECEPTIVE = "deceptive"
    COMPROMISED = "compromised"


# ─── Sub-models (Observation Components) ───────────────────────────────


class IncomingRequest(BaseModel):
    """The permission request from an autonomous agent."""

    agent_id: str = Field(..., description="Unique identifier of the requesting agent")
    agent_name: str = Field(..., description="Human-readable name of the agent")
    intended_action: str = Field(
        ..., description="What the agent wants to do (e.g., 'DROP TABLE users')"
    )
    target_resource: str = Field(
        ..., description="Specific resource being targeted (e.g., 'prod-db-primary')"
    )
    resource_type: ResourceType = Field(
        ..., description="Category of the target resource"
    )
    urgency: UrgencyLevel = Field(
        ..., description="How urgent the agent claims this request is"
    )
    justification: str = Field(
        ..., description="The agent's stated reason for the request"
    )
    associated_ticket: Optional[str] = Field(
        default=None, description="Linked Jira/incident ticket ID, if any"
    )


class AgentHistoryEntry(BaseModel):
    """A single historical action taken by the requesting agent."""

    action: str = Field(..., description="What the agent did")
    target: str = Field(..., description="What resource was targeted")
    timestamp: str = Field(..., description="When this action occurred (ISO-8601)")
    outcome: str = Field(
        ..., description="Result of the action (e.g., 'SUCCESS', 'BLOCKED')"
    )


class IAMPolicyContext(BaseModel):
    """The relevant company security policy snippet for this request."""

    policy_id: str = Field(..., description="Internal policy identifier")
    policy_name: str = Field(..., description="Human-readable policy name")
    policy_text: str = Field(..., description="The actual policy rule text")
    applicable_roles: List[str] = Field(
        default_factory=list, description="IAM roles this policy applies to"
    )
    exceptions: List[str] = Field(
        default_factory=list, description="Documented exceptions to this policy"
    )


class ActiveIncident(BaseModel):
    """An active incident affecting the infrastructure."""

    incident_id: str = Field(..., description="Incident tracking ID")
    severity: str = Field(..., description="Severity level (Sev-1 through Sev-5)")
    title: str = Field(..., description="Brief incident description")
    affected_services: List[str] = Field(
        default_factory=list, description="Services impacted by this incident"
    )


class RewardBreakdown(BaseModel):
    """
    Fine-grained reward decomposition for RL training signal.

    Each component is independently computed and testable:
      - decision_correctness: Was the terminal action right? (0.00-0.50)
      - investigation_quality: Appropriate investigation depth? (0.00-0.25)
      - reasoning_quality: Structured reasoning with evidence? (0.00-0.15)
      - urgency_awareness: Response speed matched urgency? (0.00-0.10)
    """

    decision_correctness: float = Field(
        default=0.0, description="Score for choosing the correct terminal action"
    )
    investigation_quality: float = Field(
        default=0.0, description="Score for investigating the right amount"
    )
    reasoning_quality: float = Field(
        default=0.0, description="Score for structured reasoning citing evidence"
    )
    urgency_awareness: float = Field(
        default=0.0, description="Score for response speed vs urgency match"
    )
    total: float = Field(
        default=0.0, description="Sum of all components (clamped to [0.0, 1.0])"
    )
    explanation: str = Field(
        default="", description="Human-readable explanation of the reward"
    )


# ─── Core OpenEnv Models ──────────────────────────────────────────────


class AgentGuardAction(Action):
    """
    Action for the AgentGuard environment.

    The Safety Reviewer agent must choose one of four discrete actions
    and may provide a reasoning string (used for logging/grading transparency).
    """

    decision: ActionType = Field(..., description="The permission decision")
    reasoning: str = Field(
        default="", description="Free-text explanation for the decision"
    )


class AgentGuardObservation(Observation):
    """
    Observation from the AgentGuard environment.

    Provides the Safety Reviewer with all context needed to make a
    permission governance decision.
    """

    # Core request context
    incoming_request: Optional[IncomingRequest] = Field(
        default=None, description="The agent's permission request to evaluate"
    )
    agent_history: List[AgentHistoryEntry] = Field(
        default_factory=list, description="Historical actions by this agent"
    )
    iam_policy_context: Optional[IAMPolicyContext] = Field(
        default=None, description="Relevant company security policy"
    )
    active_incidents: List[ActiveIncident] = Field(
        default_factory=list, description="Currently active infrastructure incidents"
    )

    # Episode / scenario context
    task_id: str = Field(
        default="", description="Identifier for the current task/scenario"
    )
    task_difficulty: Optional[TaskDifficulty] = Field(
        default=None, description="Difficulty tier of the current task"
    )
    scenario_description: str = Field(
        default="", description="High-level description of the scenario"
    )
    step_number: int = Field(
        default=0, description="Current step within a multi-step scenario"
    )
    total_steps: int = Field(
        default=1, description="Total steps in this scenario"
    )
    feedback: str = Field(
        default="", description="Feedback from the previous action, if any"
    )
    investigation_depth: int = Field(
        default=0, description="Number of REQUEST_INFO actions used so far"
    )
    available_info: List[str] = Field(
        default_factory=list,
        description="Information categories still available to reveal via REQUEST_INFO",
    )

    # Reward decomposition (populated on terminal decision)
    reward_breakdown: Optional[RewardBreakdown] = Field(
        default=None,
        description="Fine-grained reward decomposition (only on terminal step)",
    )

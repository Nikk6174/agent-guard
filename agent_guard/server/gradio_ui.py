"""
AgentGuard V3 — Gradio Demo UI.

Provides an interactive web interface for judges/users to:
  1. Select scenarios by difficulty tier and run them manually
  2. See 4-dimension reward breakdowns as visual bar charts
  3. View investigation layers revealed during gameplay
  4. Compare performance across scenarios

Usage:
    uv run python -m server.gradio_ui                  # standalone
    uv run python -m server.gradio_ui --share          # public Gradio link
"""

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_agent_guard_dir = os.path.dirname(_here)
sys.path.insert(0, _agent_guard_dir)

try:
    from ..models import ActionType, AgentGuardAction
    from .agent_guard_environment import AgentGuardEnvironment
    from .scenarios import SCENARIOS, SCENARIO_ORDER
except (ImportError, ModuleNotFoundError):
    try:
        from agent_guard.models import ActionType, AgentGuardAction
        from agent_guard.server.agent_guard_environment import AgentGuardEnvironment
        from agent_guard.server.scenarios import SCENARIOS, SCENARIO_ORDER
    except (ImportError, ModuleNotFoundError):
        from models import ActionType, AgentGuardAction
        from server.agent_guard_environment import AgentGuardEnvironment
        from server.scenarios import SCENARIOS, SCENARIO_ORDER

import gradio as gr

# ─── State Management ──────────────────────────────────────────────────

_env = AgentGuardEnvironment()
_current_obs = None
_episode_history = []
_episode_rewards = []


def _format_obs_markdown(obs) -> str:
    """Convert observation to rich Markdown for display."""
    lines = []

    # Header
    lines.append(f"## 🎯 {obs.task_id}")
    lines.append(f"**Difficulty:** `{obs.task_difficulty.value if obs.task_difficulty else '?'}` "
                 f"| **Step:** {obs.step_number}/{obs.total_steps} "
                 f"| **Investigation depth:** {obs.investigation_depth}")
    lines.append(f"\n*{obs.scenario_description}*\n")

    # Feedback
    if obs.feedback:
        lines.append(f"### 📋 Feedback")
        lines.append(f"> {obs.feedback}\n")

    # Request
    if obs.incoming_request:
        req = obs.incoming_request
        lines.append("### 📨 Incoming Request")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| Agent | **{req.agent_name}** (`{req.agent_id}`) |")
        lines.append(f"| Action | `{req.intended_action}` |")
        lines.append(f"| Target | `{req.target_resource}` ({req.resource_type.value}) |")
        lines.append(f"| Urgency | **{req.urgency.value}** |")
        lines.append(f"| Ticket | {req.associated_ticket or '❌ NONE'} |")
        lines.append(f"\n**Justification:** {req.justification}\n")

    # Policy
    if obs.iam_policy_context:
        pol = obs.iam_policy_context
        lines.append(f"### 📜 Policy: {pol.policy_name} (`{pol.policy_id}`)")
        lines.append(f"> {pol.policy_text}")
        if pol.applicable_roles:
            lines.append(f"\n**Roles:** {', '.join(pol.applicable_roles)}")
        if pol.exceptions:
            lines.append(f"\n**Exceptions:** {'; '.join(pol.exceptions)}")
        lines.append("")

    # History
    if obs.agent_history:
        lines.append(f"### 📊 Agent History ({len(obs.agent_history)} entries)")
        for e in obs.agent_history:
            lines.append(f"- `[{e.timestamp}]` {e.action} → {e.target} — **{e.outcome}**")
        lines.append("")

    # Incidents
    if obs.active_incidents:
        lines.append("### 🚨 Active Incidents")
        for inc in obs.active_incidents:
            lines.append(f"- **[{inc.severity}]** `{inc.incident_id}`: {inc.title}")
            if inc.affected_services:
                lines.append(f"  - Affected: {', '.join(inc.affected_services)}")
        lines.append("")

    # Available info
    if obs.available_info:
        lines.append("### 🔒 Available Information (use REQUEST_INFO)")
        for info in obs.available_info:
            lines.append(f"- 🔒 {info}")
    else:
        lines.append("### ✅ All information revealed — make your decision!")

    return "\n".join(lines)


def _format_reward_chart(obs):
    """Generate reward breakdown data for bar chart."""
    if not obs.reward_breakdown:
        return None
    rb = obs.reward_breakdown
    return {
        "Category": ["Decision\n(0.50)", "Investigation\n(0.25)", "Reasoning\n(0.15)", "Urgency\n(0.10)"],
        "Score": [rb.decision_correctness, rb.investigation_quality, rb.reasoning_quality, rb.urgency_awareness],
        "Max": [0.50, 0.25, 0.15, 0.10],
    }


def reset_scenario(scenario_id: str):
    """Reset environment with selected scenario."""
    global _current_obs, _episode_history, _episode_rewards
    _episode_history = []
    _episode_rewards = []

    obs = _env.reset(scenario_id=scenario_id)
    _current_obs = obs

    status = f"🟢 Episode started: **{obs.task_id}** ({obs.task_difficulty.value})"
    return _format_obs_markdown(obs), status, None, "Episode started"


def take_action(decision: str, reasoning: str):
    """Execute an action and return updated state."""
    global _current_obs, _episode_history, _episode_rewards

    if _current_obs is None or _current_obs.done:
        return (
            "⚠️ No active episode. Select a scenario and click Reset.",
            "⚠️ No active episode",
            None,
            "No active episode",
        )

    action_type = ActionType(decision)
    action = AgentGuardAction(decision=action_type, reasoning=reasoning)

    obs = _env.step(action)
    _current_obs = obs
    _episode_history.append(f"**{decision}**: {reasoning[:100]}")

    if obs.reward is not None:
        _episode_rewards.append(obs.reward)

    # Build status
    if obs.done:
        total = sum(_episode_rewards)
        status = f"🏁 Episode complete! Total reward: **{total:.3f}**"
        if obs.reward_breakdown:
            rb = obs.reward_breakdown
            status += (
                f"\n\n**Reward Breakdown:**\n"
                f"- Decision: {rb.decision_correctness:.2f}/0.50\n"
                f"- Investigation: {rb.investigation_quality:.2f}/0.25\n"
                f"- Reasoning: {rb.reasoning_quality:.2f}/0.15\n"
                f"- Urgency: {rb.urgency_awareness:.2f}/0.10\n"
                f"- **Total: {rb.total:.2f}/1.00**"
            )
    else:
        status = f"Step {obs.step_number} complete. Reward so far: {sum(_episode_rewards):.3f}"

    # Reward chart
    chart_data = _format_reward_chart(obs) if obs.done else None

    # History
    history = "\n".join(f"{i+1}. {h}" for i, h in enumerate(_episode_history))

    return _format_obs_markdown(obs), status, chart_data, history


def build_ui():
    """Build the Gradio Blocks interface."""

    # Organize scenarios by difficulty
    easy = [s for s in SCENARIO_ORDER if SCENARIOS[s]["difficulty"] == "easy"]
    medium = [s for s in SCENARIO_ORDER if SCENARIOS[s]["difficulty"] == "medium"]
    hard = [s for s in SCENARIO_ORDER if SCENARIOS[s]["difficulty"] == "hard"]

    with gr.Blocks(
        title="AgentGuard V3 — Adversarial Permission Governance",
        theme=gr.themes.Soft(
            primary_hue="blue",
            secondary_hue="slate",
            neutral_hue="slate",
        ),
        css="""
        .main-header { text-align: center; margin-bottom: 1rem; }
        .reward-box { border: 2px solid #4CAF50; border-radius: 8px; padding: 1rem; }
        """,
    ) as demo:
        gr.Markdown(
            """
            # 🛡️ AgentGuard V3 — Adversarial Permission Governance Simulator
            **Meta OpenEnv Hackathon Submission** | 13 scenarios × 4-dimension rewards × Multi-phase adversarial

            Train RL agents to be Security Reviewers that detect deceptive, compromised, or honest autonomous agents
            requesting permissions in enterprise infrastructure.
            """,
            elem_classes="main-header",
        )

        with gr.Row():
            # Left panel: Controls
            with gr.Column(scale=1):
                gr.Markdown("### 🎮 Controls")
                scenario_dropdown = gr.Dropdown(
                    choices=[("--- Easy ---", "")] + [(s, s) for s in easy]
                    + [("--- Medium ---", "")] + [(s, s) for s in medium]
                    + [("--- Hard ---", "")] + [(s, s) for s in hard],
                    label="Select Scenario",
                    value=easy[0] if easy else "",
                )
                reset_btn = gr.Button("🔄 Reset Scenario", variant="primary")

                gr.Markdown("### ⚡ Action")
                decision_radio = gr.Radio(
                    choices=["REQUEST_INFO", "APPROVE", "DENY", "ESCALATE"],
                    label="Decision",
                    value="REQUEST_INFO",
                )
                reasoning_text = gr.Textbox(
                    label="Reasoning (cite policy + evidence)",
                    placeholder="e.g., SEC-DB-001 requires a change ticket, and none was provided...",
                    lines=3,
                )
                action_btn = gr.Button("▶️ Submit Action", variant="secondary")

                gr.Markdown("### 📈 Status")
                status_md = gr.Markdown("Select a scenario and click Reset to begin.")

            # Right panel: Observation + Rewards
            with gr.Column(scale=2):
                gr.Markdown("### 🔍 Environment Observation")
                obs_md = gr.Markdown("*No active episode. Select a scenario and click Reset.*")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### 📊 Reward Breakdown")
                        reward_chart = gr.BarPlot(
                            x="Category",
                            y="Score",
                            title="4-Dimension Reward Decomposition",
                            y_lim=[0, 0.55],
                            height=280,
                        )
                    with gr.Column():
                        gr.Markdown("### 📝 Action History")
                        history_md = gr.Markdown("*No actions taken yet.*")

        # Wire up events
        reset_btn.click(
            fn=reset_scenario,
            inputs=[scenario_dropdown],
            outputs=[obs_md, status_md, reward_chart, history_md],
        )
        action_btn.click(
            fn=take_action,
            inputs=[decision_radio, reasoning_text],
            outputs=[obs_md, status_md, reward_chart, history_md],
        )

    return demo


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true", help="Create public Gradio link")
    parser.add_argument("--port", type=int, default=7860, help="Port to run on")
    args = parser.parse_args()

    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=args.port, share=args.share)

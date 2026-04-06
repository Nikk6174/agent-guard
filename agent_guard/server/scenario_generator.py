"""
AgentGuard V3 — Procedural Scenario Generator.

Transforms the 13 base scenarios into seed-parameterized templates
that generate unique episode variants for RL training at scale.

Design:
    - Surface randomization only: agent names, resources, tickets, timestamps
    - Scoring rubric STRUCTURE is preserved exactly (decision_scores, urgency, etc.)
    - Same seed → same variant (deterministic via seeded RNG)
    - Different seeds → different variants (meaningful diversity)

Usage:
    from scenario_generator import generate_variant
    variant = generate_variant(base_scenario, seed=42)
"""

import copy
import os
import random
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════
# NAME / RESOURCE POOLS — Curated, domain-specific alternatives
# ═══════════════════════════════════════════════════════════════════════

AGENT_ROLE_POOL = {
    "dp-bot": [
        "DataPipeline Bot", "ETLWorker", "BatchProcessor",
        "DataMover", "SchemaManager", "StreamProcessor",
    ],
    "db-admin": [
        "DBAdmin", "DatabaseOps", "SchemaBot",
        "DataStoreManager", "DBMigrator", "TableManager",
    ],
    "cred-rotator": [
        "CredentialRotator", "SecKeyManager", "KeyVaultBot",
        "IAMHelper", "AuthBot", "CertManager",
    ],
    "backup-svc": [
        "BackupService", "SnapshotBot", "ArchiveManager",
        "RecoveryBot", "StorageGuard", "VaultKeeper",
    ],
    "analytics": [
        "AnalyticsBot", "InsightWorker", "MetricsCollector",
        "DataAnalyzer", "ReportGen", "DashboardBot",
    ],
    "cicd-bot": [
        "CICDBot", "PipelineRunner", "BuildBot",
        "DeployAgent", "ReleaseManager", "ArtifactBuilder",
    ],
    "config-mgr": [
        "ConfigManager", "InfraBot", "SettingsManager",
        "NetworkOps", "SysConfigurator", "NetAdmin",
    ],
    "svc-acct-mgr": [
        "ServiceAccountMgr", "SvcIdentityBot", "AccountLifecycle",
        "CredentialOps", "IAMOps", "IdentityBot",
    ],
    "debug-assist": [
        "DebugAssistant", "LogAnalyzer", "TracingBot",
        "DiagBot", "TroubleshootBot", "ErrorHunter",
    ],
    "data-eng": [
        "DataEngineer", "DataOps", "LakeManager",
        "PipelineBot", "DataMigrator", "WarehouseBot",
    ],
    "api-mgr": [
        "APIManager", "GatewayOps", "EndpointManager",
        "TrafficController", "APIGuard", "RouteManager",
    ],
    "deploy-bot": [
        "DeployBot", "ReleaseAgent", "HotfixRunner",
        "PatchManager", "ShipItBot", "RolloutBot",
    ],
    "comms-bot": [
        "CommsBot", "ForumManager", "NotifyBot",
        "AlertDispatcher", "BroadcastBot", "AnnouncerBot",
    ],
    "sre-auto": [
        "SREAuto", "RollbackBot", "IncidentResponder",
        "AutoHealer", "ResilienceBot", "StabilityBot",
    ],
}

RESOURCE_POOLS = {
    "DATABASE": [
        "prod-db-primary", "prod-db-west-2", "prod-db-eu-1",
        "prod-db-us-east", "prod-db-central", "prod-db-ap-south",
        "prod-db-replica-3", "main-db-prod",
    ],
    "S3_BUCKET": [
        "analytics-team-raw", "data-lake-prod", "ml-datasets-v2",
        "etl-staging-bucket", "warehouse-exports", "reporting-data-prod",
    ],
    "API_ENDPOINT": [
        "api-gateway-prod", "edge-api-primary", "internal-api-v2",
        "public-api-us", "graphql-gateway-prod", "rest-api-primary",
    ],
    "LOG_SYSTEM": [
        "log-aggregator-prod", "elk-cluster-primary", "splunk-prod-main",
        "datadog-log-forwarder", "loki-prod-us", "centralized-logs-v3",
    ],
    "FIREWALL": [
        "prod-firewall-primary", "edge-fw-west", "core-fw-east-2",
        "perimeter-fw-main", "dmz-firewall-prod", "gateway-fw-primary",
    ],
    "PACKAGE_REGISTRY": [
        "prod-package-registry", "artifact-repo-main", "internal-pypi-prod",
        "npm-registry-prod", "container-registry-v2", "maven-repo-primary",
    ],
    "CODE_REPOSITORY": [
        "platform-core-repo", "backend-services-mono", "api-gateway-repo",
        "infra-as-code-main", "frontend-app-repo", "shared-libs-repo",
    ],
    "INTERNAL_FORUM": [
        "internal-forum.company.com", "eng-discuss.internal",
        "devtalk.corp.net", "team-forum-prod", "collab-hub.corp",
    ],
    "CI_CD_PIPELINE": [
        "main-cicd-pipeline", "deploy-pipeline-prod", "build-pipeline-v3",
        "release-pipeline-main", "staging-cicd-runner",
    ],
    "EXTERNAL_VENDOR_API": [
        "external-vendor-api.acme-analytics.com",
        "vendor-api.datalytics.io",
        "partner-api.cloudmetrics.com",
        "external-api.logwise.net",
        "vendor-service.analytica.io",
    ],
}

# Justification synonym pools for light paraphrasing
JUSTIFICATION_SYNONYMS = {
    "scheduled": ["planned", "routine", "pre-approved", "calendar-scheduled"],
    "migration": ["migration", "transition", "cutover", "transfer"],
    "requires": ["requires", "needs", "necessitates", "demands"],
    "legacy": ["legacy", "deprecated", "outdated", "old-format"],
    "critical": ["critical", "urgent", "high-priority", "time-sensitive"],
    "routine": ["routine", "standard", "regular", "normal"],
    "emergency": ["emergency", "urgent", "time-critical", "expedited"],
    "investigating": ["investigating", "diagnosing", "analyzing", "troubleshooting"],
    "failed": ["failed", "broke", "crashed", "errored"],
    "blocked": ["blocked", "halted", "stalled", "stuck"],
    "expired": ["expired", "lapsed", "timed out", "no longer valid"],
    "renewal": ["renewal", "reactivation", "extension", "refresh"],
    "accessing": ["accessing", "reading", "querying", "fetching"],
}


# ═══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════


def _randomize_agent_identity(
    rng: random.Random, original_id: str, original_name: str
) -> Tuple[str, str]:
    """Generate a new agent ID and name preserving the role archetype."""
    match = re.match(r"agent-(.+)-(\d+)$", original_id)
    if not match:
        num = rng.randint(1, 999)
        return f"{original_id}-v{num}", f"{original_name} {num}"

    role_key = match.group(1)
    num = rng.randint(1, 999)

    if role_key in AGENT_ROLE_POOL:
        name_base = rng.choice(AGENT_ROLE_POOL[role_key])
    else:
        name_parts = original_name.rsplit(" ", 1)
        name_base = name_parts[0] if len(name_parts) > 1 else original_name

    return f"agent-{role_key}-{num}", f"{name_base} {num}"


def _randomize_ticket(rng: random.Random, original_ticket: str) -> str:
    """Generate a new ticket ID preserving the prefix format."""
    if not original_ticket:
        return original_ticket

    # Handle compound prefixes like "AUDIT-FW-2026" → "AUDIT-FW-{N}"
    parts = original_ticket.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        num = rng.randint(1000, 99999)
        return f"{parts[0]}-{num}"

    return original_ticket


def _randomize_resource(
    rng: random.Random, resource_type: str, original: str
) -> str:
    """Pick a different resource name from the pool for this type."""
    pool = RESOURCE_POOLS.get(resource_type, [])
    if not pool:
        return original
    alternatives = [r for r in pool if r != original]
    return rng.choice(alternatives) if alternatives else original


def _shift_timestamp(timestamp_str: str, offset_hours: int) -> str:
    """Shift an ISO timestamp by offset hours while preserving format."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        shifted = dt + timedelta(hours=offset_hours)
        return shifted.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, AttributeError):
        return timestamp_str


def _randomize_policy_id(rng: random.Random, original_id: str) -> str:
    """Randomize the numeric suffix of SEC-XX-NNN style policy IDs."""
    match = re.match(r"^(SEC-[A-Z]+-)\d+$", original_id)
    if match:
        return f"{match.group(1)}{rng.randint(1, 99):03d}"
    return original_id


def _randomize_pii_counts(rng: random.Random, text: str) -> str:
    """Randomize PII record counts in warning strings."""
    def _vary(match):
        orig = int(match.group(1))
        lo = max(10, int(orig * 0.5))
        hi = int(orig * 1.5)
        return str(rng.randint(lo, hi))

    text = re.sub(r"(\d+)( PII records)", lambda m: f"{_vary(m)}{m.group(2)}", text)
    text = re.sub(r"(\d+)( email addresses)", lambda m: f"{_vary(m)}{m.group(2)}", text)
    text = re.sub(r"(\d+)( full\s+names)", lambda m: f"{_vary(m)}{m.group(2)}", text)
    text = re.sub(r"(\d+)( IP addresses)", lambda m: f"{_vary(m)}{m.group(2)}", text)
    text = re.sub(r"(\d+)( phone numbers)", lambda m: f"{_vary(m)}{m.group(2)}", text)
    text = re.sub(r"(\d+)( partial SSN)", lambda m: f"{_vary(m)}{m.group(2)}", text)
    return text


def _paraphrase(rng: random.Random, text: str) -> str:
    """Light synonym substitution on justification text."""
    words = text.split()
    result = []
    for word in words:
        lower = word.lower().strip(".,;:!?")
        if lower in JUSTIFICATION_SYNONYMS and rng.random() < 0.3:
            syns = [s for s in JUSTIFICATION_SYNONYMS[lower] if s != lower]
            if syns:
                repl = rng.choice(syns)
                if word[0].isupper():
                    repl = repl[0].upper() + repl[1:]
                trailing = ""
                for ch in reversed(word):
                    if ch in ".,;:!?":
                        trailing = ch + trailing
                    else:
                        break
                result.append(repl + trailing)
                continue
        result.append(word)
    return " ".join(result)


# ═══════════════════════════════════════════════════════════════════════
# CORE GENERATOR
# ═══════════════════════════════════════════════════════════════════════


def generate_variant(base_scenario: dict, seed: int) -> dict:
    """
    Generate a procedural variant of a base scenario.

    Surface-level details are randomized while preserving:
      - decision_scores, optimal_investigation_depth, urgency
      - Phase transitions (approve_continues, info_layers)
      - Difficulty and agent_intent classifications
      - reasoning_evidence_refs (semantic keywords)

    Args:
        base_scenario: One of the 13 base scenario dicts.
        seed: Integer seed for deterministic generation.

    Returns:
        Deep copy with randomized surface details.
    """
    rng = random.Random(seed)
    scenario = copy.deepcopy(base_scenario)

    # ── 1. Compute consistent replacement values ──

    first_req = scenario["phases"][0]["initial_data"]["incoming_request"]
    orig_agent_id = first_req["agent_id"]
    orig_agent_name = first_req["agent_name"]
    new_agent_id, new_agent_name = _randomize_agent_identity(
        rng, orig_agent_id, orig_agent_name
    )

    orig_ticket = first_req.get("associated_ticket")
    new_ticket = _randomize_ticket(rng, orig_ticket) if orig_ticket else None

    time_offset = rng.randint(-720, 720)  # ±30 days in hours
    policy_map: Dict[str, str] = {}  # old_policy_id → new_policy_id

    # Append seed to task_id for traceability
    scenario["task_id"] = f"{base_scenario['task_id']}__seed{seed}"

    # ── 2. Apply to each phase ──

    for phase in scenario["phases"]:
        req = phase["initial_data"]["incoming_request"]
        rubric = phase["scoring_rubric"]

        # Agent identity (consistent across phases)
        req["agent_id"] = new_agent_id
        req["agent_name"] = new_agent_name

        # Ticket ID (consistent across phases)
        if req.get("associated_ticket") and orig_ticket:
            req["associated_ticket"] = new_ticket

        # Resource name
        old_resource = req["target_resource"]
        new_resource = _randomize_resource(
            rng, req["resource_type"], old_resource
        )
        req["target_resource"] = new_resource

        # Justification paraphrasing
        req["justification"] = _paraphrase(rng, req["justification"])

        # ── Layer data updates ──
        for layer_name, layer_data in phase.get("layer_data", {}).items():
            # Policy ID randomization
            if "iam_policy_context" in layer_data:
                ctx = layer_data["iam_policy_context"]
                old_pid = ctx["policy_id"]
                if old_pid not in policy_map:
                    policy_map[old_pid] = _randomize_policy_id(rng, old_pid)
                ctx["policy_id"] = policy_map[old_pid]

            # Shift timestamps in history
            if "agent_history" in layer_data:
                for entry in layer_data["agent_history"]:
                    entry["timestamp"] = _shift_timestamp(
                        entry["timestamp"], time_offset
                    )
                    if entry["target"] == old_resource:
                        entry["target"] = new_resource

            # Randomize incident IDs
            if "active_incidents" in layer_data:
                for incident in layer_data["active_incidents"]:
                    parts = incident["incident_id"].rsplit("-", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        incident["incident_id"] = (
                            f"{parts[0]}-{rng.randint(100, 9999)}"
                        )

        # ── Update rubric policy refs to match new IDs ──
        new_refs = []
        for ref in rubric.get("reasoning_policy_refs", []):
            new_refs.append(policy_map.get(ref, ref))
        rubric["reasoning_policy_refs"] = new_refs

        # ── Randomize PII warnings ──
        if "pii_warning" in phase["initial_data"]:
            phase["initial_data"]["pii_warning"] = _randomize_pii_counts(
                rng, phase["initial_data"]["pii_warning"]
            )

        # ── Update agent name in feedback text ──
        for key, fb_text in phase.get("feedback", {}).items():
            if isinstance(fb_text, str):
                phase["feedback"][key] = fb_text.replace(
                    orig_agent_name, new_agent_name
                )

    return scenario


# ═══════════════════════════════════════════════════════════════════════
# SELF-TEST — run with: python scenario_generator.py
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from scenarios import SCENARIOS, SCENARIO_ORDER, MAX_PHASES_PER_EPISODE

    print("=" * 70)
    print("  Scenario Generator — Self-Test Suite")
    print("=" * 70)

    # Test 1: Determinism
    print("\n--- Test 1: Determinism ---")
    base = SCENARIOS["easy_unauthorized_db_drop"]
    v1 = generate_variant(base, seed=42)
    v2 = generate_variant(base, seed=42)
    assert v1 == v2, "Same seed must produce identical variants"
    print("  ✓ Same seed → identical variants")

    # Test 2: Diversity
    print("\n--- Test 2: Diversity ---")
    v3 = generate_variant(base, seed=43)
    assert v1 != v3, "Different seeds must differ"
    r1 = v1["phases"][0]["initial_data"]["incoming_request"]
    r3 = v3["phases"][0]["initial_data"]["incoming_request"]
    assert r1["agent_id"] != r3["agent_id"]
    print(f"  ✓ Seed 42: {r1['agent_name']}")
    print(f"  ✓ Seed 43: {r3['agent_name']}")

    # Test 3: Structure preservation across all 13 scenarios
    print("\n--- Test 3: Structure preservation ---")
    for task_id, base_s in SCENARIOS.items():
        var = generate_variant(base_s, seed=12345)
        assert len(var["phases"]) == len(base_s["phases"])
        assert var["difficulty"] == base_s["difficulty"]
        assert var["agent_intent"] == base_s["agent_intent"]
        for i, (vp, bp) in enumerate(zip(var["phases"], base_s["phases"])):
            assert vp["scoring_rubric"]["decision_scores"] == \
                   bp["scoring_rubric"]["decision_scores"]
            assert vp["scoring_rubric"]["optimal_investigation_depth"] == \
                   bp["scoring_rubric"]["optimal_investigation_depth"]
            assert vp["scoring_rubric"]["urgency"] == \
                   bp["scoring_rubric"]["urgency"]
            assert vp.get("approve_continues") == bp.get("approve_continues")
            assert vp["info_layers"] == bp["info_layers"]
            assert set(vp["feedback"].keys()) == set(bp["feedback"].keys())
        assert len(var["phases"]) <= MAX_PHASES_PER_EPISODE
    print(f"  ✓ All {len(SCENARIOS)} scenarios produce valid variants")

    # Test 4: Task ID traceability
    print("\n--- Test 4: Task ID traceability ---")
    v = generate_variant(base, seed=999)
    assert "__seed999" in v["task_id"]
    print(f"  ✓ Task ID: {v['task_id']}")

    # Test 5: Policy ref consistency
    print("\n--- Test 5: Policy ref consistency ---")
    for task_id, base_s in SCENARIOS.items():
        var = generate_variant(base_s, seed=7777)
        for i, phase in enumerate(var["phases"]):
            refs = set(phase["scoring_rubric"]["reasoning_policy_refs"])
            for ld in phase.get("layer_data", {}).values():
                if "iam_policy_context" in ld:
                    pid = ld["iam_policy_context"]["policy_id"]
                    assert pid in refs, \
                        f"{task_id} phase {i}: {pid} not in refs {refs}"
    print(f"  ✓ Policy refs consistent across all scenarios")

    # Test 6: Scale — 1000 unique variants
    print("\n--- Test 6: Scale (1000 variants) ---")
    ids = set()
    for s in range(1000):
        vv = generate_variant(base, seed=s)
        ids.add(vv["phases"][0]["initial_data"]["incoming_request"]["agent_id"])
    print(f"  ✓ 1000 seeds → {len(ids)} unique agent IDs")

    # Test 7: Multi-phase consistency
    print("\n--- Test 7: Multi-phase agent consistency ---")
    multi = SCENARIOS["hard_cascading_pii_leak"]
    mv = generate_variant(multi, seed=42)
    assert mv["phases"][0]["initial_data"]["incoming_request"]["agent_id"] == \
           mv["phases"][1]["initial_data"]["incoming_request"]["agent_id"]
    print(f"  ✓ Agent consistent across {len(mv['phases'])} phases")

    print("\n" + "=" * 70)
    print("  All generator tests passed! ✅")
    print("=" * 70)

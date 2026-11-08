"""Structured Audit Logging for GitOps Verification Decisions."""

import json
from datetime import datetime, timezone
from typing import List
from .models import CanaryPhase, VerificationDecision, GitOpsAppState


class AuditLogger:
    """Renders structured JSON and Markdown audit summaries."""

    @staticmethod
    def render_markdown(
        phase: CanaryPhase,
        decisions: List[VerificationDecision],
        app_state: GitOpsAppState,
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        status_badge = (
            "🟢 **SUCCESS: Canary Promoted to 100% Production**"
            if phase == CanaryPhase.PROMOTED_100
            else "🚨 **AUTO-ROLLBACK TRIGGERED: Error Budget / Latency Breach**"
        )

        lines = [
            "# GitOps Continuous Verification & Rollback Audit",
            f"\n**Application:** `{app_state.app_name}` | **Timestamp:** `{timestamp}`",
            f"\n## Deployment Status: {status_badge}",
            f"\n- **Stable Revision:** `{app_state.stable_revision}`",
            f"- **Target Revision:** `{app_state.target_revision}`",
            f"- **Active Traffic Weight:** `{app_state.canary_traffic_percent}%`",
            f"- **Sync Status:** `{app_state.sync_status}`",
            f"- **Health Status:** `{app_state.health_status}`",
            "\n---",
            "\n### Step-by-Step SLO Telemetry Analysis",
            "\n| Step | Latency p95 | Latency p99 | 5xx Error Rate | RPS | Gate Result |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for idx, d in enumerate(decisions, start=1):
            s = d.sample
            icon = "✅ PASSED" if d.is_healthy else "❌ BREACH"
            p95 = f"{s.latency_p95_ms:.1f}ms" if s else "N/A"
            p99 = f"{s.latency_p99_ms:.1f}ms" if s else "N/A"
            err = f"{s.error_rate_percent:.2f}%" if s else "N/A"
            rps = f"{s.rps:.1f}" if s else "N/A"
            lines.append(f"| Step {idx} | {p95} | {p99} | {err} | {rps} | {icon} |")

        if phase == CanaryPhase.ROLLED_BACK:
            lines.extend([
                "\n### 🛑 Automated Rollback Details",
                "> The autonomous controller detected an SLO breach during the verification window.",
                "> Traffic weight was instantly clamped to 0%, the Canary pod deployment was quarantined,",
                "> and ArgoCD synced back to the known stable Git commit without manual intervention.",
            ])

        return "\n".join(lines)

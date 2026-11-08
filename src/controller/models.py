"""Data models for Autonomous GitOps Continuous Verification Controller."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class CanaryPhase(str, Enum):
    PENDING = "PENDING"
    EVALUATING = "EVALUATING"
    STEP_PROMOTING = "STEP_PROMOTING"
    PROMOTED_100 = "PROMOTED_100"
    DEGRADED = "DEGRADED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class SLOThresholds:
    """Service Level Objectives (SLOs) defining production health boundaries."""
    max_p99_latency_ms: float = 250.0
    max_p95_latency_ms: float = 120.0
    max_error_rate_percent: float = 1.0  # Alert and rollback if 5xx > 1.0%
    min_rps: float = 5.0                # Ensure non-idle verification window


@dataclass
class MetricSample:
    """Prometheus telemetry sample captured during verification window."""
    timestamp: datetime
    latency_p95_ms: float
    latency_p99_ms: float
    error_rate_percent: float
    rps: float
    sample_id: str = "sample-01"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "timestamp": self.timestamp.isoformat(),
            "latency_p95_ms": self.latency_p95_ms,
            "latency_p99_ms": self.latency_p99_ms,
            "error_rate_percent": self.error_rate_percent,
            "rps": self.rps,
        }


@dataclass
class CanaryStep:
    """Traffic shifting progression step."""
    step_number: int
    traffic_percent: int
    required_passes: int = 2


@dataclass
class VerificationDecision:
    """Outcome of Prometheus metric evaluation against SLOs."""
    phase: CanaryPhase
    is_healthy: bool
    rollback_triggered: bool
    reason: str
    breached_metrics: List[str] = field(default_factory=list)
    sample: Optional[MetricSample] = None


@dataclass
class GitOpsAppState:
    """Represents live ArgoCD Application and Crossplane status."""
    app_name: str
    repo_url: str
    target_revision: str
    current_revision: str
    sync_status: str = "Synced"         # Synced | OutOfSync
    health_status: str = "Healthy"      # Healthy | Degraded | Progressing
    canary_traffic_percent: int = 0
    stable_revision: str = "v1.4.0"

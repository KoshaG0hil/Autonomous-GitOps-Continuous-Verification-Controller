"""Prometheus Metric and SLO Telemetry Evaluator."""

from typing import List
from .models import CanaryPhase, MetricSample, SLOThresholds, VerificationDecision


class MetricEvaluator:
    """Evaluates telemetry against strict Service Level Objectives (SLOs)."""

    def __init__(self, thresholds: SLOThresholds):
        self.thresholds = thresholds

    def evaluate_sample(self, sample: MetricSample) -> VerificationDecision:
        """Evaluate a single Prometheus metric sample against configured SLO gates."""
        breaches: List[str] = []

        # 1. p99 Latency Gate
        if sample.latency_p99_ms > self.thresholds.max_p99_latency_ms:
            breaches.append(
                f"p99 Latency Breach: {sample.latency_p99_ms:.1f}ms exceeds threshold of {self.thresholds.max_p99_latency_ms:.1f}ms"
            )

        # 2. p95 Latency Gate
        if sample.latency_p95_ms > self.thresholds.max_p95_latency_ms:
            breaches.append(
                f"p95 Latency Breach: {sample.latency_p95_ms:.1f}ms exceeds threshold of {self.thresholds.max_p95_latency_ms:.1f}ms"
            )

        # 3. HTTP 5xx Error Rate Gate
        if sample.error_rate_percent > self.thresholds.max_error_rate_percent:
            breaches.append(
                f"Error Budget Depletion: 5xx error rate {sample.error_rate_percent:.2f}% exceeds SLO threshold of {self.thresholds.max_error_rate_percent:.2f}%"
            )

        # 4. Traffic Volume Gate (guards against false positives under zero load)
        if sample.rps < self.thresholds.min_rps:
            breaches.append(
                f"Insufficient Load: {sample.rps:.1f} RPS is below minimum verification threshold of {self.thresholds.min_rps:.1f} RPS"
            )

        if breaches:
            return VerificationDecision(
                phase=CanaryPhase.ROLLING_BACK,
                is_healthy=False,
                rollback_triggered=True,
                reason="SLO gate violation detected. Triggering immediate automated rollback.",
                breached_metrics=breaches,
                sample=sample,
            )

        return VerificationDecision(
            phase=CanaryPhase.STEP_PROMOTING,
            is_healthy=True,
            rollback_triggered=False,
            reason="All SLO gates passed (p99 latency, p95 latency, error budget, throughput).",
            breached_metrics=[],
            sample=sample,
        )

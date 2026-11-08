"""Unit and integration tests for Autonomous GitOps Continuous Verification Controller."""

import pytest
from datetime import datetime, timezone
from src.controller.models import (
    CanaryPhase,
    CanaryStep,
    GitOpsAppState,
    MetricSample,
    SLOThresholds,
)
from src.controller.metric_evaluator import MetricEvaluator
from src.controller.gitops_reconciler import GitOpsReconciler
from src.controller.canary_controller import ContinuousVerificationController
from src.controller.audit_logger import AuditLogger


@pytest.fixture
def thresholds():
    return SLOThresholds(
        max_p99_latency_ms=250.0,
        max_p95_latency_ms=120.0,
        max_error_rate_percent=1.0,
        min_rps=10.0,
    )


@pytest.fixture
def evaluator(thresholds):
    return MetricEvaluator(thresholds)


@pytest.fixture
def healthy_sample():
    return MetricSample(
        timestamp=datetime.now(timezone.utc),
        latency_p95_ms=60.0,
        latency_p99_ms=130.0,
        error_rate_percent=0.15,
        rps=120.0,
        sample_id="healthy-sample",
    )


@pytest.fixture
def app_state():
    return GitOpsAppState(
        app_name="payment-service",
        repo_url="https://github.com/KoshaG0hil/gitops-deployments",
        target_revision="v2.1.0-canary",
        current_revision="v2.0.0",
        stable_revision="v2.0.0",
        sync_status="Synced",
        health_status="Healthy",
        canary_traffic_percent=0,
    )


# ==========================================================
# 1. Metric Evaluator Tests
# ==========================================================

def test_metric_evaluator_all_pass(evaluator, healthy_sample):
    decision = evaluator.evaluate_sample(healthy_sample)
    assert decision.is_healthy is True
    assert decision.rollback_triggered is False
    assert decision.phase == CanaryPhase.STEP_PROMOTING
    assert len(decision.breached_metrics) == 0


def test_metric_evaluator_p99_latency_breach(evaluator, healthy_sample):
    healthy_sample.latency_p99_ms = 350.0  # Limit is 250.0
    decision = evaluator.evaluate_sample(healthy_sample)
    assert decision.is_healthy is False
    assert decision.rollback_triggered is True
    assert decision.phase == CanaryPhase.ROLLING_BACK
    assert any("p99 Latency Breach" in b for b in decision.breached_metrics)


def test_metric_evaluator_p95_latency_breach(evaluator, healthy_sample):
    healthy_sample.latency_p95_ms = 145.0  # Limit is 120.0
    decision = evaluator.evaluate_sample(healthy_sample)
    assert decision.is_healthy is False
    assert decision.rollback_triggered is True
    assert any("p95 Latency Breach" in b for b in decision.breached_metrics)


def test_metric_evaluator_error_rate_breach(evaluator, healthy_sample):
    healthy_sample.error_rate_percent = 2.4  # Limit is 1.0%
    decision = evaluator.evaluate_sample(healthy_sample)
    assert decision.is_healthy is False
    assert decision.rollback_triggered is True
    assert any("Error Budget Depletion" in b for b in decision.breached_metrics)


def test_metric_evaluator_insufficient_load(evaluator, healthy_sample):
    healthy_sample.rps = 2.0  # Min is 10.0
    decision = evaluator.evaluate_sample(healthy_sample)
    assert decision.is_healthy is False
    assert decision.rollback_triggered is True
    assert any("Insufficient Load" in b for b in decision.breached_metrics)


# ==========================================================
# 2. GitOps Reconciler Tests
# ==========================================================

def test_gitops_reconciler_traffic_shifting(app_state):
    reconciler = GitOpsReconciler(app_state)
    reconciler.set_traffic_weight(25)
    assert app_state.canary_traffic_percent == 25
    assert app_state.health_status == "Progressing"


def test_gitops_reconciler_automated_rollback(app_state):
    reconciler = GitOpsReconciler(app_state)
    reconciler.set_traffic_weight(50)
    reconciler.trigger_automated_rollback("p99 latency breach")

    assert app_state.canary_traffic_percent == 0
    assert app_state.current_revision == "v2.0.0"
    assert app_state.target_revision == "v2.0.0"
    assert "Healthy (Rolled Back)" in app_state.health_status


def test_gitops_reconciler_promotion(app_state):
    reconciler = GitOpsReconciler(app_state)
    reconciler.promote_to_100_percent()

    assert app_state.canary_traffic_percent == 100
    assert app_state.stable_revision == "v2.1.0-canary"
    assert app_state.health_status == "Healthy"


# ==========================================================
# 3. Continuous Verification Controller Lifecycle Tests
# ==========================================================

def test_canary_controller_healthy_progression(app_state, evaluator):
    reconciler = GitOpsReconciler(app_state)
    controller = ContinuousVerificationController(reconciler=reconciler, evaluator=evaluator)

    now = datetime.now(timezone.utc)
    healthy_samples = [
        MetricSample(now, latency_p95_ms=50.0, latency_p99_ms=100.0, error_rate_percent=0.1, rps=50.0),
        MetricSample(now, latency_p95_ms=55.0, latency_p99_ms=110.0, error_rate_percent=0.1, rps=100.0),
        MetricSample(now, latency_p95_ms=60.0, latency_p99_ms=120.0, error_rate_percent=0.1, rps=150.0),
        MetricSample(now, latency_p95_ms=65.0, latency_p99_ms=130.0, error_rate_percent=0.1, rps=200.0),
    ]

    phase, audit = controller.run_verification_cycle(healthy_samples)
    assert phase == CanaryPhase.PROMOTED_100
    assert len(audit) == 4
    assert app_state.canary_traffic_percent == 100
    assert app_state.stable_revision == "v2.1.0-canary"


def test_canary_controller_degraded_automated_rollback(app_state, evaluator):
    reconciler = GitOpsReconciler(app_state)
    controller = ContinuousVerificationController(reconciler=reconciler, evaluator=evaluator)

    now = datetime.now(timezone.utc)
    mixed_samples = [
        MetricSample(now, latency_p95_ms=50.0, latency_p99_ms=100.0, error_rate_percent=0.1, rps=50.0),
        MetricSample(now, latency_p95_ms=55.0, latency_p99_ms=110.0, error_rate_percent=0.1, rps=100.0),
        # Failure on step 3 (50% traffic)
        MetricSample(now, latency_p95_ms=290.0, latency_p99_ms=450.0, error_rate_percent=4.5, rps=150.0),
    ]

    phase, audit = controller.run_verification_cycle(mixed_samples)
    assert phase == CanaryPhase.ROLLED_BACK
    assert len(audit) == 3
    assert app_state.canary_traffic_percent == 0
    assert app_state.current_revision == "v2.0.0"  # Rolled back to stable!


# ==========================================================
# 4. Audit Logger Tests
# ==========================================================

def test_audit_logger_render(app_state, evaluator):
    reconciler = GitOpsReconciler(app_state)
    controller = ContinuousVerificationController(reconciler=reconciler, evaluator=evaluator)
    now = datetime.now(timezone.utc)
    samples = [
        MetricSample(now, latency_p95_ms=50.0, latency_p99_ms=100.0, error_rate_percent=0.1, rps=50.0),
    ]
    phase, audit = controller.run_verification_cycle(samples)
    md = AuditLogger.render_markdown(phase, audit, app_state)
    assert "GitOps Continuous Verification & Rollback Audit" in md
    assert "payment-service" in md

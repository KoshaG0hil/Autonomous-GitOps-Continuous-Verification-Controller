#!/usr/bin/env python3
"""Autonomous GitOps Continuous Verification Controller CLI."""

import argparse
import json
import sys
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


def get_default_setup():
    app_state = GitOpsAppState(
        app_name="checkout-payment-api",
        repo_url="https://github.com/KoshaG0hil/payment-microservice-gitops",
        target_revision="v2.1.0-canary",
        current_revision="v2.0.0",
        stable_revision="v2.0.0",
        sync_status="Synced",
        health_status="Healthy",
        canary_traffic_percent=0,
    )
    reconciler = GitOpsReconciler(app_state)
    thresholds = SLOThresholds(
        max_p99_latency_ms=250.0,
        max_p95_latency_ms=120.0,
        max_error_rate_percent=1.0,
        min_rps=10.0,
    )
    evaluator = MetricEvaluator(thresholds)
    return app_state, reconciler, evaluator


def cmd_simulate(args):
    print("=" * 65)
    print(" [GitOps Controller] Autonomous Continuous Verification Cycle")
    print("=" * 65)

    app_state, reconciler, evaluator = get_default_setup()
    controller = ContinuousVerificationController(reconciler=reconciler, evaluator=evaluator)

    now = datetime.now(timezone.utc)
    if args.mode == "healthy":
        print("[*] Simulating HEALTHY Canary Rollout (10% -> 25% -> 50% -> 100%)...\n")
        samples = [
            MetricSample(now, latency_p95_ms=45.0, latency_p99_ms=95.0, error_rate_percent=0.05, rps=25.0, sample_id="step1-10pct"),
            MetricSample(now, latency_p95_ms=52.0, latency_p99_ms=110.0, error_rate_percent=0.08, rps=50.0, sample_id="step2-25pct"),
            MetricSample(now, latency_p95_ms=58.0, latency_p99_ms=125.0, error_rate_percent=0.10, rps=100.0, sample_id="step3-50pct"),
            MetricSample(now, latency_p95_ms=64.0, latency_p99_ms=140.0, error_rate_percent=0.12, rps=200.0, sample_id="step4-100pct"),
        ]
    else:
        print("[*] Simulating DEGRADED Canary Rollout (Failure injection at Step 3)...\n")
        samples = [
            MetricSample(now, latency_p95_ms=45.0, latency_p99_ms=95.0, error_rate_percent=0.05, rps=25.0, sample_id="step1-10pct"),
            MetricSample(now, latency_p95_ms=52.0, latency_p99_ms=110.0, error_rate_percent=0.08, rps=50.0, sample_id="step2-25pct"),
            # Injected failure: p99 latency 480ms (limit 250ms) and error rate 3.8% (limit 1.0%)
            MetricSample(now, latency_p95_ms=280.0, latency_p99_ms=480.0, error_rate_percent=3.80, rps=95.0, sample_id="step3-50pct-breach"),
        ]

    final_phase, decisions = controller.run_verification_cycle(samples)

    for idx, d in enumerate(decisions, start=1):
        status = "PASSED" if d.is_healthy else "BREACH"
        print(f"[{status}] Step {idx} ({d.sample.sample_id})")
        print(f"         p95: {d.sample.latency_p95_ms:.1f}ms | p99: {d.sample.latency_p99_ms:.1f}ms | 5xx: {d.sample.error_rate_percent:.2f}%")
        print(f"         Decision: {d.phase.value} | Reason: {d.reason}\n")

    print("-" * 65)
    print(f"Final Deployment Phase : {final_phase.value}")
    print(f"Application Status     : {app_state.health_status}")
    print(f"Active Git Revision    : {app_state.current_revision}")
    print(f"Canary Traffic Weight  : {app_state.canary_traffic_percent}%\n")

    if final_phase == CanaryPhase.PROMOTED_100:
        print("[+] SUCCESS: Deployment passed all continuous verification gates and was promoted.")
    elif final_phase == CanaryPhase.ROLLED_BACK:
        print("[+] SUCCESS: Autonomous controller safely intercepted failure and executed automated rollback.")


def cmd_verify(args):
    now = datetime.now(timezone.utc)
    sample = MetricSample(
        timestamp=now,
        latency_p95_ms=args.p95,
        latency_p99_ms=args.p99,
        error_rate_percent=args.error_rate,
        rps=args.rps,
    )
    thresholds = SLOThresholds(
        max_p99_latency_ms=args.max_p99,
        max_p95_latency_ms=args.max_p95,
        max_error_rate_percent=args.max_error_rate,
        min_rps=args.min_rps,
    )
    evaluator = MetricEvaluator(thresholds)
    decision = evaluator.evaluate_sample(sample)

    print("=" * 65)
    print(" [GitOps Controller] Telemetry Metric Evaluation")
    print("=" * 65)
    print(f"Healthy           : {decision.is_healthy}")
    print(f"Phase Decision    : {decision.phase.value}")
    print(f"Rollback Triggered: {decision.rollback_triggered}")
    print(f"Reason            : {decision.reason}")
    if decision.breached_metrics:
        print("Breached Metrics  :")
        for b in decision.breached_metrics:
            print(f"  - {b}")


def cmd_status(_args):
    app_state, reconciler, _ = get_default_setup()
    print("=" * 65)
    print(" [GitOps Controller] Reconciler Status")
    print("=" * 65)
    summary = reconciler.get_status_summary()
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Autonomous GitOps Continuous Verification Controller CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # simulate
    p_sim = subparsers.add_parser("simulate", help="Simulate progressive canary deployment")
    p_sim.add_argument("--mode", choices=["healthy", "degraded"], default="healthy", help="Simulation mode")
    p_sim.set_defaults(func=cmd_simulate)

    # verify
    p_ver = subparsers.add_parser("verify", help="Evaluate telemetry sample against SLOs")
    p_ver.add_argument("--p95", type=float, default=65.0)
    p_ver.add_argument("--p99", type=float, default=140.0)
    p_ver.add_argument("--error-rate", type=float, default=0.2)
    p_ver.add_argument("--rps", type=float, default=150.0)
    p_ver.add_argument("--max-p95", type=float, default=120.0)
    p_ver.add_argument("--max-p99", type=float, default=250.0)
    p_ver.add_argument("--max-error-rate", type=float, default=1.0)
    p_ver.add_argument("--min-rps", type=float, default=5.0)
    p_ver.set_defaults(func=cmd_verify)

    # status
    p_stat = subparsers.add_parser("status", help="Show reconciler status")
    p_stat.set_defaults(func=cmd_status)

    parsed = parser.parse_args()
    parsed.func(parsed)


if __name__ == "__main__":
    main()

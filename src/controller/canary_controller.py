"""Continuous Verification Canary Controller."""

from typing import List, Tuple
from .models import CanaryPhase, CanaryStep, MetricSample, VerificationDecision
from .metric_evaluator import MetricEvaluator
from .gitops_reconciler import GitOpsReconciler


class ContinuousVerificationController:
    """Controls progressive canary rollouts with continuous real-time SLO verification."""

    def __init__(
        self,
        reconciler: GitOpsReconciler,
        evaluator: MetricEvaluator,
        steps: List[CanaryStep] = None,
    ):
        self.reconciler = reconciler
        self.evaluator = evaluator
        self.steps = steps or [
            CanaryStep(step_number=1, traffic_percent=10),
            CanaryStep(step_number=2, traffic_percent=25),
            CanaryStep(step_number=3, traffic_percent=50),
            CanaryStep(step_number=4, traffic_percent=100),
        ]
        self.execution_audit: List[VerificationDecision] = []

    def run_verification_cycle(
        self,
        samples_per_step: List[MetricSample],
    ) -> Tuple[CanaryPhase, List[VerificationDecision]]:
        """Run step-by-step canary verification using provided telemetry sequence."""
        current_phase = CanaryPhase.EVALUATING

        for step_idx, step in enumerate(self.steps):
            # Shift traffic
            self.reconciler.set_traffic_weight(step.traffic_percent)

            # Evaluate sample corresponding to this step
            if step_idx < len(samples_per_step):
                sample = samples_per_step[step_idx]
            else:
                # Default fallback sample
                sample = samples_per_step[-1]

            decision = self.evaluator.evaluate_sample(sample)
            self.execution_audit.append(decision)

            if not decision.is_healthy:
                # SLO Breach: Trigger Automated Rollback Immediately
                self.reconciler.trigger_automated_rollback(
                    reason="; ".join(decision.breached_metrics)
                )
                current_phase = CanaryPhase.ROLLED_BACK
                return current_phase, self.execution_audit

        # All steps successfully completed
        self.reconciler.promote_to_100_percent()
        current_phase = CanaryPhase.PROMOTED_100
        return current_phase, self.execution_audit

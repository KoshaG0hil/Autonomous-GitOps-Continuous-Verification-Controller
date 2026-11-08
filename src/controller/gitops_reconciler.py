"""GitOps Reconciler interacting with ArgoCD and Crossplane states."""

from typing import Dict, Any
from .models import GitOpsAppState


class GitOpsReconciler:
    """Manages ArgoCD Application sync status and Crossplane infrastructure state."""

    def __init__(self, state: GitOpsAppState):
        self.state = state
        self.reconciliation_history = []

    def set_traffic_weight(self, percent: int) -> None:
        """Adjust canary traffic distribution in service mesh / ingress."""
        old_percent = self.state.canary_traffic_percent
        self.state.canary_traffic_percent = percent
        self.state.health_status = "Progressing" if percent < 100 else "Healthy"
        self._record_event(
            f"Traffic Shift: Updated canary weight from {old_percent}% to {percent}%"
        )

    def trigger_automated_rollback(self, reason: str) -> None:
        """Instantly revert traffic weight to 0% and reconcile to stable Git revision."""
        failed_revision = self.state.target_revision
        self.state.canary_traffic_percent = 0
        self.state.target_revision = self.state.stable_revision
        self.state.current_revision = self.state.stable_revision
        self.state.sync_status = "Synced"
        self.state.health_status = "Healthy (Rolled Back)"
        self._record_event(
            f"AUTOMATED ROLLBACK EXECUTED: Reverted from {failed_revision} to stable {self.state.stable_revision}. "
            f"Canary traffic isolated (0%). Reason: {reason}"
        )

    def promote_to_100_percent(self) -> None:
        """Promote canary revision to permanent stable production baseline."""
        self.state.canary_traffic_percent = 100
        self.state.stable_revision = self.state.target_revision
        self.state.current_revision = self.state.target_revision
        self.state.sync_status = "Synced"
        self.state.health_status = "Healthy"
        self._record_event(
            f"PROMOTION COMPLETE: Revision {self.state.target_revision} successfully promoted to 100% stable traffic."
        )

    def _record_event(self, message: str) -> None:
        self.reconciliation_history.append(message)

    def get_status_summary(self) -> Dict[str, Any]:
        return {
            "app_name": self.state.app_name,
            "target_revision": self.state.target_revision,
            "current_revision": self.state.current_revision,
            "stable_revision": self.state.stable_revision,
            "sync_status": self.state.sync_status,
            "health_status": self.state.health_status,
            "canary_traffic_percent": self.state.canary_traffic_percent,
        }

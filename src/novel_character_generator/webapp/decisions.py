"""Human review decision service (R11 review closed loop).

Decisions are append-only records layered *beside* immutable run artifacts:
they never rewrite raw facts, model outputs, or the projection. The service
validates that a decision targets a review item that actually exists in the
run's projection (or a registry conflict), then delegates persistence to
:class:`ReviewDecisionStore` with optimistic locking.

Current status of a review = its latest decision by revision; ``reopen`` is a
compensation decision that returns the item to the actionable queue without
deleting history.
"""

from __future__ import annotations

from typing import Any, Mapping

from .repository import RunRepository, WebRunError
from .service import WebService
from .store import ReviewDecision, ReviewDecisionStore, StoreError


class DecisionValidationError(StoreError):
    """Raised when a decision target or payload fails closed-loop validation."""


def _decision_view(decisions: list[ReviewDecision]) -> dict[str, Any] | None:
    if not decisions:
        return None
    latest = decisions[-1]
    status = "open" if latest.action == "reopen" else "decided"
    return {
        "status": status,
        "latest_action": latest.action,
        "latest_decision_id": latest.decision_id,
        "decided_by": latest.operator,
        "decided_at": latest.created_at,
        "decision_count": len(decisions),
    }


class ReviewDecisionService:
    def __init__(self, service: WebService, repository: RunRepository, store: ReviewDecisionStore) -> None:
        self._service = service
        self._repository = repository
        self._store = store

    # ----------------------------------------------------------- validation

    def _known_review_ids(self, run_id: str) -> tuple[dict[str, str], dict[str, str]]:
        """Return ({review_item_id: target_kind}, {conflict_id: target_kind})."""
        spec = self._repository.get_run(run_id)
        projection = self._repository.load_artifact(spec, "label_projection")
        registry = self._repository.load_artifact(spec, "registry")
        review_ids: dict[str, str] = {}
        conflict_ids: dict[str, str] = {}
        for key in ("actionable_review_items", "audit_items"):
            items = projection.get(key)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, Mapping) and isinstance(item.get("review_item_id"), str):
                        review_ids[item["review_item_id"]] = "review"
        characters = registry.get("characters")
        if isinstance(characters, list):
            for entry in characters:
                if not isinstance(entry, Mapping):
                    continue
                conflicts = entry.get("possible_conflicts")
                if not isinstance(conflicts, list):
                    continue
                for conflict in conflicts:
                    if isinstance(conflict, Mapping) and isinstance(conflict.get("conflict_id"), str):
                        conflict_ids[conflict["conflict_id"]] = "conflict"
        return review_ids, conflict_ids

    def _resolve_target(self, run_id: str, review_id: str) -> str:
        review_ids, conflict_ids = self._known_review_ids(run_id)
        if review_id in review_ids:
            return "review"
        if review_id in conflict_ids:
            return "conflict"
        raise DecisionValidationError(
            "review_not_found",
            f"run {run_id} has no review item or conflict with id {review_id}",
            status_code=404,
        )

    # ------------------------------------------------------------- commands

    def submit_decision(
        self,
        run_id: str,
        review_id: str,
        *,
        action: str,
        operator: str,
        note: str = "",
        payload: Mapping[str, Any] | None = None,
        expected_revision: int,
        idempotency_key: str | None = None,
    ) -> tuple[ReviewDecision, bool]:
        self._repository.get_run(run_id)  # fail closed on unknown run
        target_kind = self._resolve_target(run_id, review_id)
        payload = dict(payload or {})
        if action == "correct" and not str(payload.get("new_value") or "").strip():
            raise DecisionValidationError(
                "decision_new_value_required",
                "action 'correct' requires payload.new_value",
                status_code=422,
            )
        if action == "reopen" and not self._store.list_decisions(run_id, review_id=review_id):
            raise DecisionValidationError(
                "decision_not_decided",
                "action 'reopen' targets an undecided review; nothing to compensate",
                status_code=422,
            )
        return self._store.submit(
            run_id,
            review_id=review_id,
            target_kind=target_kind,
            action=action,
            operator=operator,
            note=note,
            payload=payload,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    # -------------------------------------------------------------- queries

    def list_decisions(self, run_id: str, *, review_id: str | None = None) -> list[ReviewDecision]:
        self._repository.get_run(run_id)
        return self._store.list_decisions(run_id, review_id=review_id)

    def current_revision(self, run_id: str) -> int:
        self._repository.get_run(run_id)
        return self._store.current_revision(run_id)

    def reviews_with_decisions(self, run_id: str) -> dict[str, Any]:
        """Project the read-only review view and layer decision status on top."""
        payload = self._service.list_reviews(run_id)
        decisions = self._store.list_decisions(run_id)
        by_review: dict[str, list[ReviewDecision]] = {}
        for decision in decisions:
            by_review.setdefault(decision.review_id, []).append(decision)
        for item in payload.get("actionable", []):
            view = _decision_view(by_review.get(str(item.get("review_item_id")), []))
            if view is not None:
                item["decision"] = view
        for item in payload.get("audit", []):
            view = _decision_view(by_review.get(str(item.get("review_item_id")), []))
            if view is not None:
                item["decision"] = view
        for entry in payload.get("open_conflicts", []):
            conflicts = entry.get("conflicts")
            if isinstance(conflicts, list):
                for conflict in conflicts:
                    if isinstance(conflict, Mapping) and isinstance(conflict.get("conflict_id"), str):
                        view = _decision_view(by_review.get(conflict["conflict_id"], []))
                        if view is not None:
                            conflict["decision"] = view
        payload["decision_revision"] = self._store.current_revision(run_id)
        pending = 0
        for item in payload.get("actionable", []):
            decision = item.get("decision")
            if decision is None or decision.get("status") == "open":
                pending += 1
        payload["pending_review_count"] = pending
        return payload

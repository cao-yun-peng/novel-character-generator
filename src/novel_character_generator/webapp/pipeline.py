"""Pipeline executor for managed jobs (R09).

Runs the full extraction chain over a stored document version by calling the
same application functions the CLI uses — never by shelling out. Stage
outputs land under ``jobs/{job_id}/stages/`` and are resumable by design: the
executor skips stages already recorded as succeeded and each stage function
itself reuses verified on-disk artifacts.

Cancellation is cooperative: the executor checks the cancel flag before each
stage and inside the progress sink, which stage functions invoke per chunk or
task. Already-issued provider calls may still finish (documented R09 policy).
"""

from __future__ import annotations

import json
import os
import re
import threading
from hashlib import sha256
from pathlib import Path
from typing import Callable

from ..appearance_scope import run_document_appearance_scope_assembly
from ..appearance_transition_batch import run_document_appearance_transitions
from ..document_evidence import run_document_evidence_aggregation
from ..fact_groups import run_document_fact_group_assembly
from ..identity_batch import run_document_identity
from ..identity_local_closure import run_local_identity_closure_replay
from ..identity_rescue_batch import run_identity_rescue
from ..label_review_projection import run_document_label_review_projection
from ..m1_batch import run_m1_document
from ..m2_batch import run_m2_from_m1_run
from ..n3_batch import run_n3_promotion_from_m2_run
from ..providers import DeepSeekProvider
from .repository import WebRunError
from .store import DocumentStore, JobRecord, JobStore, StageState, StoreError, SubjectIndex, utc_now

PROVIDER_STAGES = ("m1", "m2", "n3", "identity", "identity_rescue", "transitions")
CALL_COUNT_KEYS = ("new_provider_calls", "provider_calls", "model_calls")

ProviderFactory = Callable[[str, JobRecord], object]


class PipelineCancelled(Exception):
    """Raised inside stage progress callbacks to abort a running job."""


class PipelineError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 500) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def default_provider_factory() -> ProviderFactory:
    """Build DeepSeek providers from the server environment, one per stage."""

    def factory(stage_id: str, job: JobRecord) -> object:
        if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
            raise PipelineError(
                "provider_unconfigured",
                f"stage {stage_id} needs DEEPSEEK_API_KEY and it is not set in the server environment",
                status_code=422,
            )
        return DeepSeekProvider.from_env()

    return factory


class PipelineExecutor:
    def __init__(
        self,
        *,
        document_store: DocumentStore,
        job_store: JobStore,
        subject_index: SubjectIndex,
        provider_factory: ProviderFactory,
        managed_registry_file: Path,
        on_published: Callable[[], None] | None = None,
    ) -> None:
        self._documents = document_store
        self._jobs = job_store
        self._subjects = subject_index
        self._provider_factory = provider_factory
        self._managed_registry_file = managed_registry_file.resolve()
        self._on_published = on_published
        self._cancel_flags: dict[str, threading.Event] = {}

    # ------------------------------------------------------------ lifecycle

    def attach_cancel_flag(self, job_id: str, event: threading.Event) -> None:
        self._cancel_flags[job_id] = event

    def detach_cancel_flag(self, job_id: str) -> None:
        self._cancel_flags.pop(job_id, None)

    def _is_cancelled(self, job_id: str) -> bool:
        event = self._cancel_flags.get(job_id)
        return event is not None and event.is_set()

    def execute(self, job: JobRecord) -> JobRecord:
        """Run remaining stages of ``job`` and persist every transition."""
        version = self._documents.get_version(job.document_id, job.version_id)
        if version.document_hash != job.document_hash:
            raise PipelineError(
                "document_binding_mismatch",
                f"job {job.job_id} expects document hash {job.document_hash} but version {job.version_id} is {version.document_hash}",
            )
        text = self._documents.load_text(version)
        stages_dir = self._jobs.job_dir(job.job_id) / "stages"
        stages_dir.mkdir(parents=True, exist_ok=True)

        self._jobs.append_event(job.job_id, "job_started", data={"status": job.status})
        try:
            for stage in job.stages:
                if stage.status == "succeeded":
                    continue
                if self._is_cancelled(job.job_id):
                    raise PipelineCancelled()
                self._run_stage(job, stage, text, stages_dir)
                if job.status == "partial":
                    self._jobs.append_event(job.job_id, "job_partial")
                    return job
            job.status = "succeeded"
            job.error = None
            job.completed_at = utc_now()
            self._jobs.save(job)
            self._jobs.append_event(job.job_id, "job_succeeded", data={"run_id": job.run_id})
            self._publish(job, stages_dir)
        except PipelineCancelled:
            job.status = "cancelled"
            job.cancel_requested = False
            job.completed_at = utc_now()
            for stage in job.stages:
                if stage.status == "running":
                    stage.status = "pending"
                    stage.started_at = None
            self._jobs.save(job)
            self._jobs.append_event(job.job_id, "job_cancelled")
        except (PipelineError, StoreError, WebRunError) as error:
            self._fail(job, getattr(error, "code", "pipeline_failed"), str(error))
        except Exception as error:  # noqa: BLE001 - job boundary must capture everything
            self._fail(job, "pipeline_failed", f"{type(error).__name__}: {error}")
        return job

    def _fail(self, job: JobRecord, code: str, message: str) -> None:
        running = next((stage for stage in job.stages if stage.status == "running"), None)
        if running is not None:
            running.status = "failed"
            running.error = message
            running.completed_at = utc_now()
        job.status = "failed"
        job.error = f"{code}: {message}"
        job.completed_at = utc_now()
        self._jobs.save(job)
        self._jobs.append_event(job.job_id, "job_failed", stage_id=running.stage_id if running else None,
                                message=message, data={"code": code})

    # ---------------------------------------------------------------- stages

    def _run_stage(self, job: JobRecord, stage: StageState, text: str, stages_dir: Path) -> None:
        stage.status = "running"
        stage.started_at = utc_now()
        stage.error = None
        self._jobs.save(job)
        self._jobs.append_event(job.job_id, "stage_started", stage_id=stage.stage_id)
        try:
            summary = self._call_stage(job, stage, text, stages_dir)
        except PipelineCancelled:
            raise
        except Exception as error:
            stage.status = "failed"
            stage.error = f"{type(error).__name__}: {error}"
            stage.completed_at = utc_now()
            self._jobs.save(job)
            self._jobs.append_event(job.job_id, "stage_failed", stage_id=stage.stage_id, message=stage.error)
            raise

        stage.summary = _summary_digest(summary)
        stage.provider_calls = _provider_calls(summary)
        stage.progress_done = stage.progress_total if stage.progress_total is not None else stage.progress_done
        stage.completed_at = utc_now()
        if summary.get("complete") is False:
            stage.status = "partial"
            job.status = "partial"
            job.completed_at = utc_now()
            job.error = f"stage_partial: {stage.stage_id}"
            self._jobs.save(job)
            self._jobs.append_event(job.job_id, "stage_partial", stage_id=stage.stage_id)
            return
        stage.status = "succeeded"
        self._jobs.save(job)
        self._jobs.append_event(
            job.job_id, "stage_succeeded", stage_id=stage.stage_id,
            data={"provider_calls": stage.provider_calls, "complete": True},
        )

    def _call_stage(self, job: JobRecord, stage: StageState, text: str, stages_dir: Path) -> dict[str, object]:
        stage_dir = stages_dir / stage.stage_id
        progress = self._progress_sink(job, stage)

        if stage.stage_id == "m1":
            return run_m1_document(
                document_text=text,
                provider=self._provider(stage, job),
                output_dir=stage_dir,
                chunk_size=int(job.pipeline.get("chunk_size") or 8000),
                overlap_characters=int(job.pipeline.get("overlap_characters") or 500),
                source_document_version_id=job.version_id,
                progress=progress,
            )
        if stage.stage_id == "m2":
            return run_m2_from_m1_run(
                document_text=text,
                source_run_dir=stages_dir / "m1",
                provider=self._provider(stage, job),
                output_dir=stage_dir,
                progress=progress,
            )
        if stage.stage_id == "n3":
            return run_n3_promotion_from_m2_run(
                document_text=text,
                source_m1_run_dir=stages_dir / "m1",
                source_m2_run_dir=stages_dir / "m2",
                provider=self._provider(stage, job),
                output_dir=stage_dir,
                progress=progress,
            )
        if stage.stage_id == "evidence":
            stage_dir.mkdir(parents=True, exist_ok=True)
            return run_document_evidence_aggregation(
                document_text=text,
                source_m1_run_dir=stages_dir / "m1",
                source_m2_run_dir=stages_dir / "m2",
                source_n3_run_dir=stages_dir / "n3",
                output_file=stage_dir / "document-character-evidence.json",
            )
        if stage.stage_id == "identity":
            return run_document_identity(
                document_text=text,
                source_n2_packets_file=stages_dir / "m2" / "source-n2-grounded-packets.json",
                source_n3_run_dir=stages_dir / "n3",
                document_evidence_file=stages_dir / "evidence" / "document-character-evidence.json",
                provider=self._provider(stage, job),
                output_dir=stage_dir,
                progress=progress,
            )
        if stage.stage_id == "identity_rescue":
            seed = stage_dir / "grounded-cluster-rescue-decisions.json"
            return run_identity_rescue(
                document_text=text,
                source_identity_run_dir=stages_dir / "identity",
                provider=self._provider(stage, job),
                output_dir=stage_dir,
                seed_rescue_run_dir=stage_dir if seed.exists() else None,
                progress=progress,
            )
        if stage.stage_id == "local_closure":
            return run_local_identity_closure_replay(
                document_text=text,
                source_identity_run_dir=stages_dir / "identity",
                source_rescue_run_dir=stages_dir / "identity_rescue",
                evidence_file=stages_dir / "evidence" / "document-character-evidence.json",
                output_dir=stage_dir,
            )
        if stage.stage_id == "fact_groups":
            stage_dir.mkdir(parents=True, exist_ok=True)
            return run_document_fact_group_assembly(
                document_text=text,
                registry_file=stages_dir / "local_closure" / "document-character-registry.json",
                profiles_file=stages_dir / "local_closure" / "document-character-profiles.json",
                output_file=stage_dir / "document-character-fact-groups.json",
            )
        if stage.stage_id == "appearance_scopes":
            stage_dir.mkdir(parents=True, exist_ok=True)
            return run_document_appearance_scope_assembly(
                document_text=text,
                fact_groups_file=stages_dir / "fact_groups" / "document-character-fact-groups.json",
                output_file=stage_dir / "document-character-appearance-scopes.json",
            )
        if stage.stage_id == "transitions":
            return run_document_appearance_transitions(
                document_text=text,
                profiles_file=stages_dir / "local_closure" / "document-character-profiles.json",
                local_nodes_file=stages_dir / "identity" / "document-local-character-nodes.json",
                fact_groups_file=stages_dir / "fact_groups" / "document-character-fact-groups.json",
                scopes_file=stages_dir / "appearance_scopes" / "document-character-appearance-scopes.json",
                chunk_manifest_file=stages_dir / "m1" / "manifest.json",
                provider=self._provider(stage, job),
                output_dir=stage_dir,
                progress=progress,
            )
        if stage.stage_id == "label_projection":
            stage_dir.mkdir(parents=True, exist_ok=True)
            return run_document_label_review_projection(
                document_text=text,
                registry_file=stages_dir / "local_closure" / "document-character-registry.json",
                output_file=stage_dir / "document-character-label-review-projection.json",
            )
        raise PipelineError("stage_unknown", f"executor has no stage {stage.stage_id}")

    def _provider(self, stage: StageState, job: JobRecord) -> object:
        if stage.stage_id not in PROVIDER_STAGES:
            raise PipelineError("stage_misconfigured", f"stage {stage.stage_id} does not take a provider")
        return self._provider_factory(stage.stage_id, job)

    def _progress_sink(self, job: JobRecord, stage: StageState) -> Callable[[str], None]:
        pattern = re.compile(r"\[(\d+)/(\d+)\]")

        def sink(message: str) -> None:
            if self._is_cancelled(job.job_id):
                raise PipelineCancelled()
            match = pattern.search(message)
            if match:
                stage.progress_done = int(match.group(1))
                stage.progress_total = int(match.group(2))
            self._jobs.append_event(
                job.job_id, "stage_progress", stage_id=stage.stage_id, message=message,
                data={"done": stage.progress_done, "total": stage.progress_total},
            )

        return sink

    # -------------------------------------------------------------- publish

    def _publish(self, job: JobRecord, stages_dir: Path) -> None:
        base_dir = self._managed_registry_file.parent.parent
        artifacts = {
            "registry": stages_dir / "local_closure" / "document-character-registry.json",
            "fact_groups": stages_dir / "fact_groups" / "document-character-fact-groups.json",
            "appearance_states": stages_dir / "transitions" / "document-character-appearance-states.json",
            "label_projection": stages_dir / "label_projection" / "document-character-label-review-projection.json",
            "document_evidence": stages_dir / "evidence" / "document-character-evidence.json",
        }
        for name, path in artifacts.items():
            if not path.is_file():
                raise PipelineError("publish_artifact_missing", f"artifact {name} missing at {path}")

        registry_payload: dict[str, object] = {"schema_version": "web-run-registry-v1", "runs": []}
        if self._managed_registry_file.is_file():
            loaded = json.loads(self._managed_registry_file.read_text(encoding="utf-8"))
            if loaded.get("schema_version") != "web-run-registry-v1":
                raise PipelineError("registry_invalid", f"managed registry {self._managed_registry_file} has unsupported schema")
            registry_payload["runs"] = [run for run in loaded.get("runs", []) if run.get("run_id") != job.run_id]
        runs: list[dict[str, object]] = list(registry_payload["runs"])  # type: ignore[arg-type]
        runs.append({
            "run_id": job.run_id,
            "display_name": f"{job.display_name} · {job.version_id} · {job.job_id}",
            "input_file": _relative(base_dir, self._documents.get_version(job.document_id, job.version_id).source_path),
            "document_hash": job.document_hash,
            "source_document_version_id": job.version_id,
            "snapshot_namespace": job.run_id,
            "artifacts": {
                name: {"path": _relative(base_dir, path), "sha256": _file_sha256(path)}
                for name, path in artifacts.items()
            },
        })
        registry_payload["runs"] = runs
        temporary = self._managed_registry_file.with_name(".web-job-registry.json.tmp")
        self._managed_registry_file.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(registry_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, self._managed_registry_file)

        self._record_subjects(job, artifacts["registry"])
        self._jobs.append_event(job.job_id, "run_published", data={"run_id": job.run_id})
        if self._on_published is not None:
            self._on_published()

    def _record_subjects(self, job: JobRecord, registry_path: Path) -> None:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        characters = [entry for entry in registry.get("characters", []) if isinstance(entry, dict)]
        self._subjects.record_run(job.document_id, job.run_id, characters)


def _summary_digest(summary: object) -> dict[str, object]:
    if not isinstance(summary, dict):
        return {}
    keep = ("complete", "planned_tasks", "planned_chunks", "succeeded_tasks", "succeeded_chunks",
            "resumed_tasks", "resumed_chunks", "failed_tasks", "failed_chunks", "grounded_facts",
            "grounded_transitions", "candidate_mentions", "grounded_mentions", "global_characters",
            "review_items", "assigned_appearance_facts")
    return {key: summary[key] for key in keep if key in summary}


def _provider_calls(summary: dict[str, object]) -> int:
    for key in CALL_COUNT_KEYS:
        value = summary.get(key)
        if isinstance(value, int):
            return value
    return 0


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _relative(base_dir: Path, path: Path) -> str:
    return os.path.relpath(path.resolve(), base_dir.resolve()).replace("\\", "/")

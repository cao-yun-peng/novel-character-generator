"""FastAPI application: read-only run endpoints plus managed documents/jobs.

Read endpoints never trigger provider calls; snapshot compilation is a pure
in-process function over verified artifacts (docs/37 section 6.1). Managed
endpoints (documents/jobs/subjects) wrap :class:`JobService`; job execution
happens on a single background worker started by the app lifespan.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .decisions import ReviewDecisionService
from .jobs import JobService
from .pipeline import PipelineError, PipelineExecutor, default_provider_factory
from .repository import RunRepository, WebRunError
from .service import API_SCHEMA_VERSION, OFFSET_UNIT, WebService, validate_text_window
from .store import (
    DocumentStore,
    DocumentVersion,
    JobStore,
    ReviewDecisionStore,
    StoreError,
    SubjectIndex,
)

DEFAULT_REGISTRY_FILE = Path(__file__).resolve().parents[3] / "runs" / "web-run-registry.json"
DEFAULT_WORKSPACE_ROOT = Path(__file__).resolve().parents[3] / "runs" / "web-jobs"

MANAGED_REGISTRY_NAME = "web-job-registry.json"
JOBS_LIST_LIMIT_BOUNDS = (1, 200)


class CreateDocumentRequest(BaseModel):
    text: str
    display_name: str = ""


class CreateRunRequest(BaseModel):
    version_id: str | None = None
    pipeline: dict[str, Any] | None = None
    idempotency_key: str | None = None


class CreateDecisionRequest(BaseModel):
    action: str
    operator: str
    note: str = ""
    payload: dict[str, Any] | None = None
    expected_revision: int
    idempotency_key: str | None = None


def _request_id() -> str:
    return f"req-{uuid.uuid4().hex[:16]}"


def _error_payload(error: WebRunError | StoreError | PipelineError) -> dict[str, Any]:
    return {
        "code": error.code,
        "stage": "web",
        "retryable": False,
        "message": error.message,
    }


def _default_job_service(workspace: Path, repository: RunRepository) -> JobService:
    documents = DocumentStore(workspace)
    job_store = JobStore(workspace)
    subjects = SubjectIndex(documents)
    executor = PipelineExecutor(
        document_store=documents,
        job_store=job_store,
        subject_index=subjects,
        provider_factory=default_provider_factory(),
        managed_registry_file=workspace / MANAGED_REGISTRY_NAME,
        on_published=repository.reload,
    )
    return JobService(
        document_store=documents,
        job_store=job_store,
        subject_index=subjects,
        executor=executor,
    )


def _version_payload(version: DocumentVersion) -> dict[str, Any]:
    return {
        "version_id": version.version_id,
        "document_hash": version.document_hash,
        "code_points": version.code_points,
        "created_at": version.created_at,
    }


def _subject_payload(subject: Any) -> dict[str, Any]:
    return {
        "subject_id": subject.subject_id,
        "preferred_label": subject.preferred_label,
        "status": subject.status,
        "run_mappings": [dict(mapping) for mapping in subject.run_mappings],
    }


def create_app(
    repository: RunRepository | None = None,
    *,
    static_dir: Path | None = None,
    workspace_root: Path | None = None,
    job_service: JobService | None = None,
) -> FastAPI:
    workspace = (workspace_root or DEFAULT_WORKSPACE_ROOT).resolve()
    if repository is None:
        repository = RunRepository(
            DEFAULT_REGISTRY_FILE,
            managed_registry_file=workspace / MANAGED_REGISTRY_NAME,
        )
    service = WebService(repository)
    jobs = job_service if job_service is not None else _default_job_service(workspace, repository)
    decisions = ReviewDecisionService(service, repository, ReviewDecisionStore(workspace))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Iterator[None]:
        jobs.startup_recover()
        jobs.start()
        yield
        jobs.shutdown()

    app = FastAPI(title="novel-character-generator web", version="0.2.0.dev30", lifespan=lifespan)
    app.state.repository = repository
    app.state.service = service
    app.state.job_service = jobs
    app.state.decision_service = decisions

    @app.exception_handler(WebRunError)
    @app.exception_handler(StoreError)
    @app.exception_handler(PipelineError)
    async def handle_domain_error(request: Request, error: WebRunError | StoreError | PipelineError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or _request_id()
        return JSONResponse(
            status_code=error.status_code,
            content={
                "schema_version": API_SCHEMA_VERSION,
                "request_id": request_id,
                "error": _error_payload(error),
            },
        )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = _request_id()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    # ------------------------------------------------------------ read-only

    @app.get("/v1/runs")
    async def list_runs() -> dict[str, Any]:
        return service.list_runs()

    @app.get("/v1/runs/{run_id}/characters")
    async def list_characters(run_id: str) -> dict[str, Any]:
        return service.list_characters(run_id)

    @app.get("/v1/runs/{run_id}/characters/{character_id}/states")
    async def get_character_states(run_id: str, character_id: str) -> dict[str, Any]:
        return service.get_character_states(run_id, character_id)

    @app.get("/v1/runs/{run_id}/characters/{character_id}/snapshot")
    async def get_snapshot(
        run_id: str,
        character_id: str,
        position: int | None = None,
        life_stage: str | None = None,
        form_state: str | None = None,
        scene_state: str | None = None,
    ) -> dict[str, Any]:
        return service.build_snapshot(
            run_id, character_id, document_position=position,
            life_stage=life_stage, form_state=form_state, scene_state=scene_state,
        )

    @app.get("/v1/runs/{run_id}/characters/{character_id}/snapshot/explain")
    async def get_snapshot_explain(
        run_id: str,
        character_id: str,
        position: int | None = None,
        life_stage: str | None = None,
        form_state: str | None = None,
        scene_state: str | None = None,
    ) -> dict[str, Any]:
        return service.build_snapshot(
            run_id, character_id, document_position=position,
            life_stage=life_stage, form_state=form_state, scene_state=scene_state,
            explain=True,
        )

    @app.get("/v1/runs/{run_id}/text")
    async def get_text_window(
        run_id: str,
        start: int,
        end: int,
    ) -> dict[str, Any]:
        return service.get_text_window(run_id, start, end)

    @app.get("/v1/runs/{run_id}/reviews")
    async def list_reviews(run_id: str) -> dict[str, Any]:
        return decisions.reviews_with_decisions(run_id)

    @app.post("/v1/runs/{run_id}/reviews/{review_id}/decisions")
    async def submit_decision(
        run_id: str,
        review_id: str,
        payload: CreateDecisionRequest,
        response: Response,
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        key = idempotency_key or payload.idempotency_key
        decision, created = decisions.submit_decision(
            run_id,
            review_id,
            action=payload.action,
            operator=payload.operator,
            note=payload.note,
            payload=payload.payload,
            expected_revision=payload.expected_revision,
            idempotency_key=key,
        )
        response.status_code = 201 if created else 200
        return {
            "schema_version": API_SCHEMA_VERSION,
            "created": created,
            "decision": decision.to_dict(),
            "revision": decisions.current_revision(run_id),
        }

    @app.get("/v1/runs/{run_id}/reviews/{review_id}/decisions")
    async def list_decisions(run_id: str, review_id: str) -> dict[str, Any]:
        items = decisions.list_decisions(run_id, review_id=review_id)
        return {
            "schema_version": API_SCHEMA_VERSION,
            "run_id": run_id,
            "review_id": review_id,
            "revision": decisions.current_revision(run_id),
            "decisions": [item.to_dict() for item in items],
        }

    # ------------------------------------------------------------- documents

    @app.post("/v1/documents")
    async def create_document(payload: CreateDocumentRequest, response: Response) -> dict[str, Any]:
        version, created = jobs.documents.create_version(payload.text, display_name=payload.display_name)
        response.status_code = 201 if created else 200
        document = jobs.documents.get_document(version.document_id)
        return {
            "schema_version": API_SCHEMA_VERSION,
            "created": created,
            "document_id": document.document_id,
            "display_name": document.display_name,
            "version": _version_payload(version),
        }

    @app.get("/v1/documents")
    async def list_documents() -> dict[str, Any]:
        documents = [
            {
                "document_id": record.document_id,
                "display_name": record.display_name,
                "created_at": record.created_at,
                "latest_version_id": record.latest_version.version_id if record.latest_version else None,
                "versions": [_version_payload(version) for version in record.versions],
            }
            for record in jobs.documents.list_documents()
        ]
        return {"schema_version": API_SCHEMA_VERSION, "documents": documents}

    @app.get("/v1/documents/{document_id}/versions")
    async def list_versions(document_id: str) -> dict[str, Any]:
        record = jobs.documents.get_document(document_id)
        return {
            "schema_version": API_SCHEMA_VERSION,
            "document_id": record.document_id,
            "versions": [_version_payload(version) for version in record.versions],
        }

    @app.get("/v1/documents/{document_id}/versions/{version_id}/text")
    async def get_version_text(document_id: str, version_id: str, start: int, end: int) -> dict[str, Any]:
        version = jobs.documents.get_version(document_id, version_id)
        text = jobs.documents.load_text(version)
        validate_text_window(start, end, len(text))
        return {
            "schema_version": API_SCHEMA_VERSION,
            "document_id": document_id,
            "source_document_version_id": version_id,
            "document_hash": version.document_hash,
            "offset_unit": OFFSET_UNIT,
            "total_code_points": len(text),
            "start": start,
            "end": end,
            "text": text[start:end],
        }

    # ------------------------------------------------------------------ jobs

    @app.post("/v1/documents/{document_id}/runs")
    async def create_run(
        document_id: str,
        payload: CreateRunRequest,
        response: Response,
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        key = idempotency_key or payload.idempotency_key
        job, created = jobs.submit_job(
            document_id,
            payload.version_id,
            pipeline=payload.pipeline,
            idempotency_key=key,
        )
        response.status_code = 202 if created else 200
        return {"schema_version": API_SCHEMA_VERSION, "created": created, "job": job.to_dict()}

    @app.get("/v1/jobs")
    async def list_jobs(document_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        low, high = JOBS_LIST_LIMIT_BOUNDS
        if limit < low or limit > high:
            raise StoreError("invalid_limit", f"limit must be in [{low}, {high}]", status_code=422)
        records = jobs.list_jobs()
        if document_id is not None:
            records = [item for item in records if item.document_id == document_id]
        return {
            "schema_version": API_SCHEMA_VERSION,
            "jobs": [item.to_dict() for item in records[:limit]],
        }

    @app.get("/v1/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        return {"schema_version": API_SCHEMA_VERSION, "job": jobs.get_job(job_id).to_dict()}

    @app.get("/v1/jobs/{job_id}/events")
    async def get_job_events(job_id: str, after: int = 0) -> dict[str, Any]:
        result = jobs.get_events(job_id, after=after)
        return {"schema_version": API_SCHEMA_VERSION, **result}

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, Any]:
        return {"schema_version": API_SCHEMA_VERSION, "job": jobs.cancel_job(job_id).to_dict()}

    @app.post("/v1/jobs/{job_id}/resume")
    async def resume_job(job_id: str) -> dict[str, Any]:
        return {"schema_version": API_SCHEMA_VERSION, "job": jobs.resume_job(job_id).to_dict()}

    # -------------------------------------------------------------- subjects

    @app.get("/v1/documents/{document_id}/subjects")
    async def list_subjects(document_id: str) -> dict[str, Any]:
        jobs.documents.get_document(document_id)
        subjects = [_subject_payload(entry) for entry in jobs.subjects.list_subjects(document_id)]
        return {"schema_version": API_SCHEMA_VERSION, "document_id": document_id, "subjects": subjects}

    @app.get("/v1/documents/{document_id}/subjects/{subject_id}")
    async def get_subject(document_id: str, subject_id: str, run_id: str | None = None) -> dict[str, Any]:
        jobs.documents.get_document(document_id)
        entry = jobs.subjects.get_subject(document_id, subject_id)
        run_resolution = None
        if run_id is not None:
            matched = next(
                (dict(m) for m in entry.run_mappings if str(m.get("run_id")) == run_id),
                None,
            )
            run_resolution = {
                "run_id": run_id,
                "status": "resolved" if matched else "unmapped_in_run",
                "character_id": matched.get("character_id") if matched else None,
            }
        return {
            "schema_version": API_SCHEMA_VERSION,
            "document_id": document_id,
            "subject": _subject_payload(entry),
            "run_resolution": run_resolution,
        }

    # ---------------------------------------------------------------- static

    resolved_static = static_dir
    if resolved_static is None:
        candidate = Path(__file__).resolve().parents[3] / "web" / "dist"
        resolved_static = candidate if candidate.is_dir() else None
    if resolved_static is not None and resolved_static.is_dir():
        app.mount("/", StaticFiles(directory=resolved_static, html=True), name="static")

    return app


app = create_app()

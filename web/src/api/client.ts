import type {
  ApiErrorPayload,
  CharacterListResponse,
  CharacterStatesResponse,
  DecisionListResponse,
  DecisionSubmitResponse,
  DocumentListResponse,
  DocumentUploadResponse,
  JobDetailResponse,
  JobEventsResponse,
  JobListResponse,
  JobRecord,
  ReviewsResponse,
  RunSummary,
  Snapshot,
  SubjectsResponse,
  TextWindowResponse,
  VersionListResponse,
  VersionTextResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const payload = (await response.json()) as T | ApiErrorPayload;
  if (!response.ok) {
    const error = payload as ApiErrorPayload;
    if (error && typeof error === "object" && "error" in error) {
      throw new ApiError(response.status, error.error.code, error.error.message);
    }
    throw new ApiError(response.status, "unexpected_error", `HTTP ${response.status}`);
  }
  return payload as T;
}

async function get<T>(path: string): Promise<T> {
  return request<T>(path, { headers: { Accept: "application/json" } });
}

async function post<T>(path: string, body: unknown, options: { idempotencyKey?: string } = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
  return request<T>(path, { method: "POST", headers, body: JSON.stringify(body) });
}

export const api = {
  listRuns(): Promise<{ schema_version: string; runs: RunSummary[] }> {
    return get("/v1/runs");
  },
  listCharacters(runId: string): Promise<CharacterListResponse> {
    return get(`/v1/runs/${encodeURIComponent(runId)}/characters`);
  },
  getCharacterStates(runId: string, characterId: string): Promise<CharacterStatesResponse> {
    return get(`/v1/runs/${encodeURIComponent(runId)}/characters/${encodeURIComponent(characterId)}/states`);
  },
  getSnapshot(
    runId: string,
    characterId: string,
    position: number,
    options: { lifeStage?: string; formState?: string; sceneState?: string } = {},
  ): Promise<Snapshot> {
    const params = new URLSearchParams({ position: String(position) });
    if (options.lifeStage) params.set("life_stage", options.lifeStage);
    if (options.formState) params.set("form_state", options.formState);
    if (options.sceneState) params.set("scene_state", options.sceneState);
    return get(`/v1/runs/${encodeURIComponent(runId)}/characters/${encodeURIComponent(characterId)}/snapshot?${params}`);
  },
  getSnapshotExplain(
    runId: string,
    characterId: string,
    position: number,
    options: { lifeStage?: string; formState?: string; sceneState?: string } = {},
  ): Promise<Snapshot> {
    const params = new URLSearchParams({ position: String(position) });
    if (options.lifeStage) params.set("life_stage", options.lifeStage);
    if (options.formState) params.set("form_state", options.formState);
    if (options.sceneState) params.set("scene_state", options.sceneState);
    return get(
      `/v1/runs/${encodeURIComponent(runId)}/characters/${encodeURIComponent(characterId)}/snapshot/explain?${params}`,
    );
  },
  getTextWindow(runId: string, start: number, end: number): Promise<TextWindowResponse> {
    const params = new URLSearchParams({ start: String(start), end: String(end) });
    return get(`/v1/runs/${encodeURIComponent(runId)}/text?${params}`);
  },
  listReviews(runId: string): Promise<ReviewsResponse> {
    return get(`/v1/runs/${encodeURIComponent(runId)}/reviews`);
  },
  listDecisions(runId: string, reviewId: string): Promise<DecisionListResponse> {
    return get(
      `/v1/runs/${encodeURIComponent(runId)}/reviews/${encodeURIComponent(reviewId)}/decisions`,
    );
  },
  submitDecision(
    runId: string,
    reviewId: string,
    payload: {
      action: string;
      operator: string;
      note?: string;
      payload?: Record<string, unknown>;
      expectedRevision: number;
    },
    options: { idempotencyKey?: string } = {},
  ): Promise<DecisionSubmitResponse> {
    return post<DecisionSubmitResponse>(
      `/v1/runs/${encodeURIComponent(runId)}/reviews/${encodeURIComponent(reviewId)}/decisions`,
      {
        action: payload.action,
        operator: payload.operator,
        note: payload.note ?? "",
        payload: payload.payload ?? null,
        expected_revision: payload.expectedRevision,
      },
      options,
    );
  },
  uploadDocument(displayName: string, text: string): Promise<DocumentUploadResponse> {
    return post<DocumentUploadResponse>("/v1/documents", { display_name: displayName, text });
  },
  listDocuments(): Promise<DocumentListResponse> {
    return get("/v1/documents");
  },
  listVersions(documentId: string): Promise<VersionListResponse> {
    return get(`/v1/documents/${encodeURIComponent(documentId)}/versions`);
  },
  getVersionText(documentId: string, versionId: string, start: number, end: number): Promise<VersionTextResponse> {
    const params = new URLSearchParams({ start: String(start), end: String(end) });
    return get(
      `/v1/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/text?${params}`,
    );
  },
  createRun(
    documentId: string,
    payload: { versionId?: string; pipeline?: { chunk_size?: number; overlap_characters?: number } },
    options: { idempotencyKey?: string } = {},
  ): Promise<{ schema_version: string; created: boolean; job: JobRecord }> {
    const body: Record<string, unknown> = {};
    if (payload.versionId) body.version_id = payload.versionId;
    if (payload.pipeline) body.pipeline = payload.pipeline;
    return post(`/v1/documents/${encodeURIComponent(documentId)}/runs`, body, options);
  },
  listJobs(documentId?: string): Promise<JobListResponse> {
    const query = documentId ? `?document_id=${encodeURIComponent(documentId)}` : "";
    return get(`/v1/jobs${query}`);
  },
  getJob(jobId: string): Promise<JobDetailResponse> {
    return get(`/v1/jobs/${encodeURIComponent(jobId)}`);
  },
  getJobEvents(jobId: string, after: number): Promise<JobEventsResponse> {
    const params = new URLSearchParams({ after: String(after) });
    return get(`/v1/jobs/${encodeURIComponent(jobId)}/events?${params}`);
  },
  cancelJob(jobId: string): Promise<JobDetailResponse> {
    return post(`/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {});
  },
  resumeJob(jobId: string): Promise<JobDetailResponse> {
    return post(`/v1/jobs/${encodeURIComponent(jobId)}/resume`, {});
  },
  listSubjects(documentId: string): Promise<SubjectsResponse> {
    return get(`/v1/documents/${encodeURIComponent(documentId)}/subjects`);
  },
};

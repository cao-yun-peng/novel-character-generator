export interface Span {
  start: number;
  end: number;
}

export interface RunSummary {
  run_id: string;
  display_name: string;
  source_document_version_id: string;
  document_hash: string;
}

export interface CharacterLabel {
  label_id: string;
  label_quote: string;
  label_kind: string;
  label_stability: string;
  source_label_role: string;
  selection_status: string;
}

export interface CharacterCard {
  character_id: string;
  identity_status: string;
  canonical_label: string;
  canonical_label_status: string;
  labels: CharacterLabel[];
  state_segment_count: number;
  transition_count: number;
  open_conflict_count: number;
  actionable_review_count: number;
}

export interface CharacterListResponse {
  schema_version: string;
  run_id: string;
  source_document_version_id: string;
  characters: CharacterCard[];
}

export interface Boundary {
  position: number;
  reasons: string[];
  transition_ids: string[];
}

export interface StateSegment {
  state_segment_id: string;
  sequence_index: number;
  document_span: Span;
  life: string;
  form: string;
  scene: string;
  start_boundary: Boundary;
  end_boundary: Boundary;
  observed_fact_ids: string[];
}

export interface Transition {
  transition_id: string;
  evidence: string;
  document_span: Span;
  dimension: string;
  attribute: string;
  before: string;
  after: string;
  change: string;
}

export interface CharacterStatesResponse {
  schema_version: string;
  run_id: string;
  character_id: string;
  offset_unit: string;
  coverage_status: string;
  processed_source_end: number;
  state_segments: StateSegment[];
  transitions: Transition[];
}

export interface TextWindowResponse {
  schema_version: string;
  run_id: string;
  source_document_version_id: string;
  document_hash: string;
  offset_unit: string;
  total_code_points: number;
  start: number;
  end: number;
  text: string;
}

export interface Trait {
  trait_id: string;
  attribute: string;
  value: string;
  categories: string[];
  source_proposition_id: string;
  canonical_fact_ids: string[];
  persistence: string[];
  applicability_status: string;
  kind: string;
}

export interface ApplicabilityItem {
  canonical_fact_id: string;
  status: string;
  reason: string;
  observation_span: Span;
  valid_interval: { start: number; end: number | null };
  basis_event_ids: string[];
  persistence: string;
}

export interface ExcludedFact {
  canonical_fact_id: string;
  status: string;
  reason: string;
  observation_span: Span;
  valid_interval: { start: number; end: number | null };
  basis_event_ids: string[];
  persistence: string;
  provenance?: {
    fact_quote: string;
    document_fact_span: Span;
    source_fact_hashes: string[];
    source_occurrences: unknown[];
  };
}

export interface IdentityLabel {
  label_id: string;
  label_quote: string;
  label_kind: string;
  label_stability: string;
  selection_status: string;
}

export interface Snapshot {
  schema_version: string;
  policy_version: string;
  applicability_policy_version: string;
  snapshot_id: string;
  artifact_set_id: string;
  run_id: string;
  source_document_version_id: string;
  document_hash: string;
  offset_unit: string;
  identity_status: string;
  character_id: string;
  selector: {
    life_stage: string | null;
    form_state: string | null;
    scene_state: string | null;
    document_position: number | null;
  };
  compile_status: string;
  candidate_state_segment_ids: string[];
  selected_state_segment_id: string | null;
  selected_state: {
    life_stage: string;
    form_state: string;
    scene_state: string;
    chapter_number: number;
    document_span: Span;
  } | null;
  identity_labels: IdentityLabel[];
  active_fact_ids: string[];
  provisional_fact_ids: string[];
  transitions: Transition[];
  unresolved_conflicts: unknown[];
  provenance: Record<string, unknown>;
  compile_warnings: { code: string; message: string; related_ids: string[] }[] | null;
  active_traits: Trait[];
  provisional_traits: Trait[];
  applicability: ApplicabilityItem[];
  excluded_facts: ExcludedFact[];
  review_refs: string[];
  applicability_events: unknown[];
}

export interface ReviewItem {
  source: string;
  review_item_id?: string;
  review_type?: string;
  label_quote?: string;
  subject_character_id?: string;
  reason_code?: string;
  decision?: DecisionStatus;
  [key: string]: unknown;
}

export interface DecisionStatus {
  status: "decided" | "open";
  latest_action: string;
  latest_decision_id: string;
  decided_by: string;
  decided_at: string;
  decision_count: number;
}

export interface ReviewConflict {
  conflict_id: string;
  conflict_type?: string;
  category?: string;
  attribute?: string;
  values?: string[];
  decision?: DecisionStatus;
  [key: string]: unknown;
}

export interface ReviewsResponse {
  schema_version: string;
  run_id: string;
  actionable: ReviewItem[];
  audit: ReviewItem[];
  state_review: ReviewItem[];
  open_conflicts: { source: string; character_id: string; conflicts: ReviewConflict[] }[];
  decision_revision: number;
  pending_review_count: number;
}

export interface ReviewDecision {
  decision_id: string;
  run_id: string;
  review_id: string;
  target_kind: string;
  action: string;
  operator: string;
  note: string;
  payload: Record<string, unknown>;
  revision: number;
  idempotency_key: string | null;
  created_at: string;
}

export interface DecisionSubmitResponse {
  schema_version: string;
  created: boolean;
  decision: ReviewDecision;
  revision: number;
}

export interface DecisionListResponse {
  schema_version: string;
  run_id: string;
  review_id: string;
  revision: number;
  decisions: ReviewDecision[];
}

export interface ApiErrorPayload {
  schema_version: string;
  request_id: string;
  error: {
    code: string;
    stage: string;
    retryable: boolean;
    message: string;
  };
}

// ---------------------------------------------------------- managed documents

export interface DocumentVersionInfo {
  version_id: string;
  document_hash: string;
  code_points: number;
  created_at: string;
}

export interface DocumentSummary {
  document_id: string;
  display_name: string;
  created_at: string;
  latest_version_id: string | null;
  versions: DocumentVersionInfo[];
}

export interface DocumentUploadResponse {
  schema_version: string;
  created: boolean;
  document_id: string;
  display_name: string;
  version: DocumentVersionInfo;
}

export interface DocumentListResponse {
  schema_version: string;
  documents: DocumentSummary[];
}

export interface VersionListResponse {
  schema_version: string;
  document_id: string;
  versions: DocumentVersionInfo[];
}

export interface VersionTextResponse {
  schema_version: string;
  document_id: string;
  source_document_version_id: string;
  document_hash: string;
  offset_unit: string;
  total_code_points: number;
  start: number;
  end: number;
  text: string;
}

// --------------------------------------------------------------------- jobs

export interface JobStage {
  stage_id: string;
  name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  progress: { done: number; total: number | null };
  provider_calls: number;
  summary: Record<string, unknown>;
}

export interface JobRecord {
  schema_version: string;
  job_id: string;
  run_id: string;
  document_id: string;
  source_document_version_id: string;
  document_hash: string;
  display_name: string;
  pipeline: { chunk_size: number; overlap_characters: number };
  idempotency_key: string | null;
  status: string;
  cancel_requested: boolean;
  stages: JobStage[];
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface JobListResponse {
  schema_version: string;
  jobs: JobRecord[];
}

export interface JobDetailResponse {
  schema_version: string;
  job: JobRecord;
}

export interface JobEvent {
  seq: number;
  at: string;
  type: string;
  stage_id: string | null;
  message: string | null;
  data: Record<string, unknown>;
}

export interface JobEventsResponse {
  schema_version: string;
  job_id: string;
  after: number;
  events: JobEvent[];
  next_cursor: number;
}

// ------------------------------------------------------------------ subjects

export interface SubjectRunMapping {
  run_id: string;
  character_id: string;
  resolved_at: string;
}

export interface SubjectEntry {
  subject_id: string;
  preferred_label: string;
  status: string;
  run_mappings: SubjectRunMapping[];
}

export interface SubjectsResponse {
  schema_version: string;
  document_id: string;
  subjects: SubjectEntry[];
}

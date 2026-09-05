import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { CharacterStatesResponse, Snapshot, Trait } from "../api/types";
import TextPane, { type TextHighlight } from "../components/TextPane";
import SnapshotPane from "../components/SnapshotPane";
import EvidencePane from "../components/EvidencePane";
import SegmentTimeline from "../components/SegmentTimeline";
import { identityStatusLabels, label } from "../lib/labels";

const WINDOW_BEFORE = 400;
const WINDOW_AFTER = 1100;

export default function CharacterDetailPage() {
  const { runId, characterId } = useParams<{ runId: string; characterId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const positionParam = searchParams.get("position");

  const [states, setStates] = useState<CharacterStatesResponse | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selectedTrait, setSelectedTrait] = useState<Trait | null>(null);
  const [windowStart, setWindowStart] = useState(0);
  const [windowEnd, setWindowEnd] = useState(1500);
  const [error, setError] = useState<string | null>(null);

  const total = states?.processed_source_end ?? 0;
  const position = positionParam !== null ? Number(positionParam) : null;

  const setPosition = useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(total ? total - 1 : next, next));
      setSearchParams({ position: String(clamped) }, { replace: true });
    },
    [setSearchParams, total],
  );

  useEffect(() => {
    if (!runId || !characterId) return;
    setStates(null);
    setSnapshot(null);
    setError(null);
    api
      .getCharacterStates(runId, characterId)
      .then((payload) => {
        setStates(payload);
        if (positionParam === null) {
          const firstStart = payload.state_segments[0]?.start_boundary.position ?? 0;
          setPosition(Math.max(0, Math.min(payload.processed_source_end - 1, firstStart)));
        }
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
  }, [runId, characterId, positionParam, setPosition]);

  useEffect(() => {
    if (!runId || !characterId || position === null || !states) return;
    const timer = window.setTimeout(() => {
      api
        .getSnapshotExplain(runId, characterId, position)
        .then((payload) => {
          setSnapshot(payload);
          setSelectedTrait((current) => {
            if (!current) return null;
            const stillPresent =
              payload.active_traits.some((t) => t.trait_id === current.trait_id) ||
              payload.provisional_traits.some((t) => t.trait_id === current.trait_id);
            return stillPresent ? current : null;
          });
        })
        .catch((e: unknown) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
    }, 150);
    return () => window.clearTimeout(timer);
  }, [runId, characterId, position, states]);

  useEffect(() => {
    if (position === null || total === 0) return;
    const inCore = position >= windowStart + 50 && position < windowEnd - 50;
    if (!inCore) {
      setWindowStart(Math.max(0, position - WINDOW_BEFORE));
      setWindowEnd(Math.min(total, position - WINDOW_BEFORE + WINDOW_BEFORE + WINDOW_AFTER));
    }
  }, [position, total, windowStart, windowEnd]);

  const highlights = useMemo<TextHighlight[]>(() => {
    if (!snapshot || !states) return [];
    const result: TextHighlight[] = [];
    const activeFactIds = new Set(snapshot.active_traits.flatMap((t) => t.canonical_fact_ids));
    const provisionalFactIds = new Set(snapshot.provisional_traits.flatMap((t) => t.canonical_fact_ids));
    const selectedFactIds = new Set(selectedTrait ? selectedTrait.canonical_fact_ids : []);
    for (const item of snapshot.applicability) {
      const kind = selectedFactIds.has(item.canonical_fact_id)
        ? "selected"
        : activeFactIds.has(item.canonical_fact_id)
          ? "active"
          : provisionalFactIds.has(item.canonical_fact_id)
            ? "provisional"
            : null;
      if (kind) {
        result.push({ span: item.observation_span, kind, title: `${item.canonical_fact_id} (${item.status})` });
      }
    }
    for (const transition of states.transitions) {
      result.push({ span: transition.document_span, kind: "transition", title: `${transition.attribute}: ${transition.evidence}` });
    }
    return result;
  }, [snapshot, states, selectedTrait]);

  const jumpToSpan = useCallback(
    (span: { start: number; end: number }) => {
      setWindowStart(Math.max(0, span.start - 150));
      setWindowEnd(Math.min(total, Math.max(0, span.start - 150) + WINDOW_BEFORE + WINDOW_AFTER));
      setPosition(span.start);
    },
    [setPosition, total],
  );

  if (!runId || !characterId) return null;

  return (
    <section className="detail-page">
      <div className="detail-header">
        <Link to={`/runs/${runId}`} className="back-link">
          ← 人物列表
        </Link>
        {snapshot && (
          <span className="detail-title">
            {snapshot.identity_labels.find((l) => l.selection_status === "preferred")?.label_quote ?? characterId}
            <span className="muted small"> · {label(identityStatusLabels, snapshot.identity_status)}</span>
          </span>
        )}
        {snapshot && <span className="muted small">快照 {snapshot.snapshot_id}</span>}
      </div>
      {error && <div className="error-box">{error}</div>}
      {states && position !== null && (
        <SegmentTimeline states={states} position={position} onPositionChange={setPosition} />
      )}
      <div className="three-columns">
        <TextPane runId={runId} windowStart={windowStart} windowEnd={windowEnd} highlights={highlights} />
        {snapshot ? (
          <SnapshotPane
            snapshot={snapshot}
            selectedTraitId={selectedTrait?.trait_id ?? null}
            onSelectTrait={(trait) => setSelectedTrait((current) => (current?.trait_id === trait.trait_id ? null : trait))}
          />
        ) : (
          <div className="pane">
            <p className="muted">加载快照…</p>
          </div>
        )}
        <EvidencePane snapshot={snapshot!} selectedTrait={selectedTrait} onJumpToSpan={jumpToSpan} />
      </div>
    </section>
  );
}

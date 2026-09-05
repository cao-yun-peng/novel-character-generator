import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { CharacterCard } from "../api/types";
import {
  canonicalLabelStatusLabels,
  identityStatusLabels,
  label,
  labelKindLabels,
  labelStabilityLabels,
} from "../lib/labels";

function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-identity-${status}`}>{label(identityStatusLabels, status)}</span>;
}

export default function CharacterListPage() {
  const { runId } = useParams<{ runId: string }>();
  const [characters, setCharacters] = useState<CharacterCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    api
      .listCharacters(runId)
      .then((payload) => setCharacters(payload.characters))
      .catch((e: unknown) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)))
      .finally(() => setLoading(false));
  }, [runId]);

  return (
    <section className="page">
      <div className="page-header-row">
        <h1>人物列表</h1>
        <Link className="button" to={`/runs/${runId}/reviews`}>
          复核与审计
        </Link>
      </div>
      {loading && <p>加载中…</p>}
      {error && <div className="error-box">{error}</div>}
      <table className="character-table">
        <thead>
          <tr>
            <th>人物</th>
            <th>身份状态</th>
            <th>称呼（类型/稳定性）</th>
            <th>状态区间</th>
            <th>转换</th>
            <th>待办</th>
          </tr>
        </thead>
        <tbody>
          {characters.map((character) => (
            <tr key={character.character_id}>
              <td>
                <Link to={`/runs/${runId}/characters/${character.character_id}`} className="character-link">
                  {character.canonical_label}
                </Link>
                <div className="muted small">
                  {label(canonicalLabelStatusLabels, character.canonical_label_status)}
                </div>
              </td>
              <td>
                <StatusBadge status={character.identity_status} />
              </td>
              <td>
                {character.labels.map((entry) => (
                  <span key={entry.label_id} className="label-chip" title={`${entry.source_label_role} / ${entry.selection_status}`}>
                    {entry.label_quote}
                    <span className="label-chip-kind">
                      {label(labelKindLabels, entry.label_kind)}·{label(labelStabilityLabels, entry.label_stability)}
                    </span>
                  </span>
                ))}
              </td>
              <td className="numeric">{character.state_segment_count}</td>
              <td className="numeric">{character.transition_count}</td>
              <td className="numeric">
                {character.actionable_review_count > 0 && (
                  <span className="badge badge-review">{character.actionable_review_count} 待复核</span>
                )}
                {character.open_conflict_count > 0 && (
                  <span className="badge badge-conflict">{character.open_conflict_count} 冲突</span>
                )}
                {character.actionable_review_count === 0 && character.open_conflict_count === 0 && <span className="muted">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

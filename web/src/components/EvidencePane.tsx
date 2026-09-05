import type { Snapshot, Trait } from "../api/types";
import { applicabilityStatusLabels, exclusionReasonLabels, label, persistenceLabels } from "../lib/labels";

interface Props {
  snapshot: Snapshot;
  selectedTrait: Trait | null;
  onJumpToSpan: (span: { start: number; end: number }) => void;
}

export default function EvidencePane({ snapshot, selectedTrait, onJumpToSpan }: Props) {
  return (
    <div className="pane evidence-pane">
      <div className="pane-header">
        <h2>证据面板</h2>
      </div>

      {!selectedTrait && (
        <p className="muted">在中间栏点击一个特质查看其证据：原文观察位置、有效区间与适用状态。</p>
      )}

      {selectedTrait && (
        <>
          <div className="evidence-trait">
            <span className="trait-attribute">{selectedTrait.attribute}</span>
            <span className="trait-value">{selectedTrait.value}</span>
            <div className="muted small">
              {label(applicabilityStatusLabels, selectedTrait.applicability_status)} ·{" "}
              {selectedTrait.persistence.map((p) => label(persistenceLabels, p)).join("/")}
            </div>
          </div>

          <h4>事实证据（canonical facts）</h4>
          <ul className="evidence-list">
            {selectedTrait.canonical_fact_ids.map((factId) => {
              const applicability = snapshot.applicability.find((item) => item.canonical_fact_id === factId);
              const excluded = snapshot.excluded_facts.find((item) => item.canonical_fact_id === factId);
              const entry = applicability ?? excluded;
              if (!entry) {
                return (
                  <li key={factId} className="evidence-item">
                    <span className="muted">{factId}</span>
                    <span className="warn-box small">缺少适用性记录</span>
                  </li>
                );
              }
              return (
                <li key={factId} className="evidence-item">
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => onJumpToSpan(entry.observation_span)}
                    title="在原文窗口中定位该证据"
                  >
                    原文 [{entry.observation_span.start}, {entry.observation_span.end})
                  </button>
                  <div className="muted small">
                    状态 {label(applicabilityStatusLabels, entry.status)}
                    {entry.reason ? ` · ${label(exclusionReasonLabels, entry.reason)}` : ""}
                  </div>
                  <div className="muted small">
                    有效区间 [{entry.valid_interval.start}, {entry.valid_interval.end ?? "未定"}）
                  </div>
                  {excluded?.provenance?.fact_quote && (
                    <blockquote className="evidence-quote">{excluded.provenance.fact_quote}</blockquote>
                  )}
                </li>
              );
            })}
          </ul>

          <h4>身份标签</h4>
          <div className="label-chips">
            {snapshot.identity_labels.map((entry) => (
              <span key={entry.label_id} className="label-chip">
                {entry.label_quote}
              </span>
            ))}
          </div>

          {snapshot.review_refs.length > 0 && (
            <>
              <h4>关联复核</h4>
              <ul className="evidence-list">
                {snapshot.review_refs.map((ref) => (
                  <li key={ref} className="muted small">
                    {ref}
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="trace-placeholder">
            <h4>证据处理轨迹</h4>
            <p className="muted small">
              完整分层轨迹（M1 → N2 → M2 → N3 → promotion → M3 → canonical fact → 状态区间 → 快照）将在后续阶段接入；
              当前面板展示快照层的可追溯引用。
            </p>
            <div className="trace-chain">
              {["M1 提及", "N2 校验", "M2 归属", "N3 仲裁", "身份合并", "事实分组", "状态区间", "快照"].map(
                (stage, index) => (
                  <span key={stage} className="trace-node">
                    {stage}
                    {index < 7 && <span className="trace-arrow">→</span>}
                  </span>
                ),
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

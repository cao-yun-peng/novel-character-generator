import type { Snapshot, Trait } from "../api/types";
import { applicabilityStatusLabels, exclusionReasonLabels, label, persistenceLabels, traitKindLabels } from "../lib/labels";

interface Props {
  snapshot: Snapshot;
  selectedTraitId: string | null;
  onSelectTrait: (trait: Trait) => void;
}

function TraitRow({
  trait,
  selected,
  onSelect,
}: {
  trait: Trait;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li className={`trait trait-${trait.applicability_status} ${selected ? "trait-selected" : ""}`}>
      <button type="button" className="trait-button" onClick={onSelect}>
        <span className="trait-attribute">{trait.attribute}</span>
        <span className="trait-value">{trait.value}</span>
        <span className="trait-meta">
          {label(traitKindLabels, trait.kind)} · {trait.persistence.map((p) => label(persistenceLabels, p)).join("/")}
        </span>
      </button>
    </li>
  );
}

export default function SnapshotPane({ snapshot, selectedTraitId, onSelectTrait }: Props) {
  const excludedByReason = snapshot.excluded_facts.reduce<Record<string, number>>((acc, item) => {
    acc[item.reason] = (acc[item.reason] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="pane snapshot-pane">
      <div className="pane-header">
        <h2>人物快照</h2>
        <span className="muted small">{snapshot.snapshot_id}</span>
      </div>

      <div className="snapshot-state">
        {snapshot.selected_state ? (
          <div>
            第 {snapshot.selected_state.chapter_number} 章 · 位置 {snapshot.selector.document_position} · 区间{" "}
            [{snapshot.selected_state.document_span.start}, {snapshot.selected_state.document_span.end})
            <div className="muted small">
              life={snapshot.selected_state.life_stage} · form={snapshot.selected_state.form_state} ·
              scene={snapshot.selected_state.scene_state}
            </div>
          </div>
        ) : (
          <div className="warn-box">当前位置没有匹配的状态区间</div>
        )}
      </div>

      <section className="trait-section">
        <h3>
          确定有效 <span className="count-badge count-active">{snapshot.active_traits.length}</span>
        </h3>
        {snapshot.active_traits.length === 0 && <p className="muted">当前位置无确定有效的外貌事实</p>}
        <ul className="trait-list">
          {snapshot.active_traits.map((trait) => (
            <TraitRow
              key={trait.trait_id}
              trait={trait}
              selected={trait.trait_id === selectedTraitId}
              onSelect={() => onSelectTrait(trait)}
            />
          ))}
        </ul>
      </section>

      <section className="trait-section">
        <h3>
          暂定 <span className="count-badge count-provisional">{snapshot.provisional_traits.length}</span>
          <span className="muted small">不能默认当作确定结论</span>
        </h3>
        {snapshot.provisional_traits.length === 0 && <p className="muted">当前位置无暂定外貌事实</p>}
        <ul className="trait-list">
          {snapshot.provisional_traits.map((trait) => (
            <TraitRow
              key={trait.trait_id}
              trait={trait}
              selected={trait.trait_id === selectedTraitId}
              onSelect={() => onSelectTrait(trait)}
            />
          ))}
        </ul>
      </section>

      {(snapshot.unresolved_conflicts.length > 0 || (snapshot.compile_warnings?.length ?? 0) > 0) && (
        <section className="trait-section">
          <h3>
            冲突与警告 <span className="count-badge count-conflict">{snapshot.unresolved_conflicts.length}</span>
          </h3>
          {snapshot.compile_warnings?.map((warning, index) => (
            <div key={index} className="warn-box">
              {warning.code}: {warning.message}
            </div>
          ))}
        </section>
      )}

      <section className="trait-section">
        <details>
          <summary>
            不适用的事实（{snapshot.excluded_facts.length}） · 按原因展开
          </summary>
          <div className="excluded-reasons">
            {Object.entries(excludedByReason).map(([reason, count]) => (
              <span key={reason} className="label-chip">
                {label(exclusionReasonLabels, reason)} × {count}
              </span>
            ))}
          </div>
          <ul className="excluded-list">
            {snapshot.excluded_facts.map((item) => (
              <li key={item.canonical_fact_id}>
                <span className="muted small">{label(applicabilityStatusLabels, item.status)}</span>{" "}
                {item.provenance?.fact_quote ?? item.canonical_fact_id}
                <span className="label-chip-kind">{label(exclusionReasonLabels, item.reason)}</span>
              </li>
            ))}
          </ul>
        </details>
      </section>
    </div>
  );
}

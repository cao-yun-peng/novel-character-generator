import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type {
  DecisionStatus,
  ReviewDecision,
  ReviewItem,
  ReviewsResponse,
} from "../api/types";

type DecisionAction = "accept" | "reject" | "correct" | "reopen";

const ACTION_LABELS: Record<DecisionAction, string> = {
  accept: "接受",
  reject: "拒绝",
  correct: "纠正",
  reopen: "重开",
};

function DecisionBadge({ decision }: { decision?: DecisionStatus }) {
  if (!decision) return <span className="badge badge-review">待办</span>;
  if (decision.status === "open") {
    return (
      <span className="badge badge-review">
        已重开（{decision.decision_count} 次决策）
      </span>
    );
  }
  return (
    <span className="badge badge-job-succeeded">
      {ACTION_LABELS[decision.latest_action as DecisionAction] ?? decision.latest_action}（{decision.decided_by}）
    </span>
  );
}

function DecisionHistory({ runId, reviewId }: { runId: string; reviewId: string }) {
  const [history, setHistory] = useState<ReviewDecision[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listDecisions(runId, reviewId)
      .then((payload) => setHistory(payload.decisions))
      .catch((e: unknown) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
  }, [runId, reviewId]);

  if (error) return <p className="error-box">{error}</p>;
  if (history === null) return <p className="muted small">加载决策历史…</p>;
  if (history.length === 0) return <p className="muted small">尚无决策记录。</p>;
  return (
    <ul className="decision-history">
      {history.map((item) => (
        <li key={item.decision_id}>
          <span className="badge">{ACTION_LABELS[item.action as DecisionAction] ?? item.action}</span>
          <span className="small">rev {item.revision} · {item.operator} · {item.created_at}</span>
          {item.note && <blockquote className="evidence-quote small">{item.note}</blockquote>}
          {item.payload.new_value ? (
            <p className="small">新值：{String(item.payload.new_value)}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function DecisionForm({
  runId,
  reviewId,
  expectedRevision,
  operator,
  hasDecision,
  decidedStatus,
  onDone,
}: {
  runId: string;
  reviewId: string;
  expectedRevision: number;
  operator: string;
  hasDecision: boolean;
  decidedStatus: string | null;
  onDone: () => void;
}) {
  const [action, setAction] = useState<DecisionAction>("accept");
  const [note, setNote] = useState("");
  const [newValue, setNewValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.submitDecision(
        runId,
        reviewId,
        {
          action,
          operator,
          note,
          payload: action === "correct" ? { new_value: newValue } : undefined,
          expectedRevision,
        },
        { idempotencyKey: `web-${Date.now()}-${reviewId}` },
      );
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.code === "version_conflict") {
        setError("决策版本冲突：列表已被他人更新，正在刷新…");
        onDone();
      } else {
        setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="decision-form">
      <div className="form-field-row">
        <div className="form-field">
          <label>动作</label>
          <select value={action} onChange={(event) => setAction(event.target.value as DecisionAction)}>
            <option value="accept">接受（确认现状）</option>
            <option value="reject">拒绝（标记误报）</option>
            <option value="correct">纠正（提供新值）</option>
            {hasDecision && <option value="reopen">重开（补偿撤销）</option>}
          </select>
        </div>
        {action === "correct" && (
          <div className="form-field">
            <label>新值 *</label>
            <input
              value={newValue}
              placeholder="例如：正确的标签或取值"
              onChange={(event) => setNewValue(event.target.value)}
            />
          </div>
        )}
      </div>
      <div className="form-field">
        <label>依据说明（可选）</label>
        <textarea
          rows={2}
          value={note}
          placeholder="说明判断依据，如原文位置、语义理由…"
          onChange={(event) => setNote(event.target.value)}
        />
      </div>
      {decidedStatus && (
        <p className="muted small">
          该项已有决策（{decidedStatus}）；新决策追加记录，最新一条生效。
        </p>
      )}
      <div className="form-actions">
        <button
          className="button"
          disabled={busy || !operator.trim() || (action === "correct" && !newValue.trim())}
          onClick={submit}
        >
          {busy ? "提交中…" : "提交决策"}
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
    </div>
  );
}

export default function ReviewsPage() {
  const { runId = "" } = useParams<{ runId: string }>();
  const [reviews, setReviews] = useState<ReviewsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [operator, setOperator] = useState("");
  const [openReview, setOpenReview] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .listReviews(runId)
      .then(setReviews)
      .catch((e: unknown) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)));
  }, [runId]);

  useEffect(refresh, [refresh]);

  const renderActionable = (item: ReviewItem) => {
    const reviewId = item.review_item_id;
    if (!reviewId) return null;
    const decision = item.decision;
    const isOpen = openReview === reviewId;
    return (
      <li key={reviewId} className="review-item review-actionable">
        <div className="review-item-row">
          <span className="badge badge-review">{String(item.review_type ?? "")}</span>
          {typeof item.subject_character_id === "string" && (
            <Link
              to={`/runs/${runId}/characters/${item.subject_character_id}`}
              className="character-link"
            >
              {String(item.label_quote ?? item.subject_character_id)}
            </Link>
          )}
          <span className="muted small">{String(item.reason_code ?? "")}</span>
          <DecisionBadge decision={decision} />
          <button className="link-button" onClick={() => setOpenReview(isOpen ? null : reviewId)}>
            {isOpen ? "收起" : "决策 / 历史"}
          </button>
        </div>
        {isOpen && reviews && (
          <div className="review-item-detail">
            <DecisionForm
              runId={runId}
              reviewId={reviewId}
              expectedRevision={reviews.decision_revision}
              operator={operator}
              hasDecision={Boolean(decision)}
              decidedStatus={decision ? ACTION_LABELS[decision.latest_action as DecisionAction] ?? null : null}
              onDone={refresh}
            />
            <DecisionHistory runId={runId} reviewId={reviewId} />
          </div>
        )}
      </li>
    );
  };

  return (
    <section className="page">
      <div className="page-header-row">
        <h1>复核与审计</h1>
        <Link className="button" to={`/runs/${runId}`}>
          ← 人物列表
        </Link>
      </div>
      {error && <div className="error-box">{error}</div>}

      <div className="pane">
        <div className="form-field-row">
          <div className="form-field">
            <label htmlFor="operator">操作者</label>
            <input
              id="operator"
              value={operator}
              placeholder="你的名字（决策记录必填）"
              onChange={(event) => setOperator(event.target.value)}
            />
          </div>
          {reviews && (
            <p className="muted small">
              决策日志版本 rev {reviews.decision_revision} · 待办{" "}
              <span className="count-badge count-review">{reviews.pending_review_count}</span> / 共{" "}
              {reviews.actionable.length} 项
            </p>
          )}
        </div>
        <p className="muted small">
          决策为追加式记录：不修改原文事实与模型输出，最新决策生效，重开通过补偿决策完成。
        </p>
      </div>

      {reviews && (
        <>
          <section>
            <h2>
              当前待办 <span className="count-badge count-review">{reviews.pending_review_count}</span>
            </h2>
            {reviews.actionable.length === 0 && <p className="muted">无待办复核</p>}
            <ul className="review-list">
              {reviews.actionable.map((item) => renderActionable(item))}
            </ul>
          </section>

          <section>
            <h2>
              身份审计历史 <span className="count-badge">{reviews.audit.length}</span>
            </h2>
            <p className="muted small">历史复核记录，仅供审计；已被最终身份图消解的条目不再列入待办。</p>
            <ul className="review-list">
              {reviews.audit.map((item, index) => (
                <li key={item.review_item_id ?? index} className="review-item">
                  <span className="badge">{String(item.review_type ?? "")}</span>
                  <span>{String(item.label_quote ?? "")}</span>
                  <span className="muted small">{String(item.subject_character_id ?? "")}</span>
                  <DecisionBadge decision={item.decision} />
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2>
              状态层复核 <span className="count-badge">{reviews.state_review.length}</span>
            </h2>
            <p className="muted small">状态层复核项暂无稳定 ID，本轮不支持决策提交，仅供查看。</p>
            <ul className="review-list">
              {reviews.state_review.map((item, index) => (
                <li key={index} className="review-item">
                  <span className="badge">{String(item.reason ?? "")}</span>
                  <span>{String(item.character ?? "")}</span>
                  <blockquote className="evidence-quote">{String(item.evidence ?? "")}</blockquote>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2>未消解冲突</h2>
            {reviews.open_conflicts.length === 0 && <p className="muted">无</p>}
            <ul className="review-list">
              {reviews.open_conflicts.map((entry) => (
                <li key={entry.character_id} className="review-item review-actionable">
                  <Link to={`/runs/${runId}/characters/${entry.character_id}`} className="character-link">
                    {entry.character_id}
                  </Link>
                  <ul className="conflict-list">
                    {entry.conflicts.map((conflict) => {
                      const isOpen = openReview === conflict.conflict_id;
                      return (
                        <li key={conflict.conflict_id}>
                          <div className="review-item-row">
                            <span className="badge">
                              {String(conflict.conflict_type ?? "")} · {String(conflict.attribute ?? "")}
                            </span>
                            <span className="small">{(conflict.values ?? []).join(" / ")}</span>
                            <DecisionBadge decision={conflict.decision} />
                            <button
                              className="link-button"
                              onClick={() => setOpenReview(isOpen ? null : conflict.conflict_id)}
                            >
                              {isOpen ? "收起" : "决策 / 历史"}
                            </button>
                          </div>
                          {isOpen && (
                            <div className="review-item-detail">
                              <DecisionForm
                                runId={runId}
                                reviewId={conflict.conflict_id}
                                expectedRevision={reviews.decision_revision}
                                operator={operator}
                                hasDecision={Boolean(conflict.decision)}
                                decidedStatus={
                                  conflict.decision
                                    ? ACTION_LABELS[conflict.decision.latest_action as DecisionAction] ?? null
                                    : null
                                }
                                onDone={refresh}
                              />
                              <DecisionHistory runId={runId} reviewId={conflict.conflict_id} />
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </section>
  );
}

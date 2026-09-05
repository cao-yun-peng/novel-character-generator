import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { DocumentSummary, JobRecord, SubjectEntry } from "../api/types";

const TERMINAL_JOB_STATUSES = new Set(["succeeded", "partial", "failed", "cancelled"]);

export default function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState<DocumentSummary | null>(null);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [subjects, setSubjects] = useState<SubjectEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [versionId, setVersionId] = useState("");
  const [chunkSize, setChunkSize] = useState(8000);
  const [overlap, setOverlap] = useState(500);
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [documentsPayload, jobsPayload, subjectsPayload] = await Promise.all([
        api.listDocuments(),
        api.listJobs(documentId),
        api.listSubjects(documentId),
      ]);
      const found = documentsPayload.documents.find((item) => item.document_id === documentId) ?? null;
      if (!found) {
        setError("document_not_found: 未知文档");
        return;
      }
      setDocument(found);
      setJobs(jobsPayload.jobs);
      setSubjects(subjectsPayload.subjects);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  }, [documentId]);

  useEffect(() => {
    setLoading(true);
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    const hasActive = jobs.some((job) => !TERMINAL_JOB_STATUSES.has(job.status));
    if (!hasActive) return;
    const handle = setInterval(refresh, 3000);
    return () => clearInterval(handle);
  }, [jobs, refresh]);

  useEffect(() => {
    if (!versionId && document?.latest_version_id) setVersionId(document.latest_version_id);
  }, [document, versionId]);

  const startRun = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const payload = await api.createRun(documentId, {
        versionId: versionId || undefined,
        pipeline: { chunk_size: chunkSize, overlap_characters: overlap },
      });
      navigate(`/jobs/${payload.job.job_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <section className="page">
        <p>加载中…</p>
      </section>
    );
  }

  return (
    <section className="page">
      <div className="detail-header">
        <Link className="back-link" to="/documents">
          ← 文档库
        </Link>
      </div>
      <h1>{document?.display_name ?? documentId}</h1>
      <p className="page-hint">
        文档 <span className="numeric">{documentId}</span>
        {document?.latest_version_id && (
          <>
            {" "}
            · 最新来源版本 <span className="numeric">{document.latest_version_id}</span>
          </>
        )}
      </p>
      {error && <div className="error-box">{error}</div>}

      <div className="two-columns">
        <div className="pane">
          <div className="pane-header">
            <h2>来源版本</h2>
          </div>
          <table className="character-table">
            <thead>
              <tr>
                <th>version_id</th>
                <th>code points</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {(document?.versions ?? []).map((version) => (
                <tr key={version.version_id}>
                  <td className="numeric">{version.version_id}</td>
                  <td className="numeric">{version.code_points}</td>
                  <td className="small">{version.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="pane">
          <div className="pane-header">
            <h2>启动解析任务</h2>
          </div>
          <div className="form-field">
            <label htmlFor="version-select">来源版本</label>
            <select id="version-select" value={versionId} onChange={(event) => setVersionId(event.target.value)}>
              {(document?.versions ?? []).map((version) => (
                <option key={version.version_id} value={version.version_id}>
                  {version.version_id}（{version.code_points} cp）
                </option>
              ))}
            </select>
          </div>
          <div className="form-field-row">
            <div className="form-field">
              <label htmlFor="chunk-size">chunk_size</label>
              <input
                id="chunk-size"
                type="number"
                min={1000}
                max={200000}
                value={chunkSize}
                onChange={(event) => setChunkSize(Number(event.target.value))}
              />
            </div>
            <div className="form-field">
              <label htmlFor="overlap">overlap_characters</label>
              <input
                id="overlap"
                type="number"
                min={0}
                max={20000}
                value={overlap}
                onChange={(event) => setOverlap(Number(event.target.value))}
              />
            </div>
          </div>
          <div className="form-actions">
            <button className="button" disabled={submitting || !versionId} onClick={startRun}>
              {submitting ? "提交中…" : "启动解析（12 阶段流水线）"}
            </button>
          </div>
          <p className="muted small">
            同一版本同时只允许一个活动任务；重复提交返回冲突。任务支持取消与断点恢复。
          </p>
        </div>
      </div>

      <div className="pane">
        <div className="pane-header">
          <h2>解析任务</h2>
        </div>
        {jobs.length === 0 && <p className="muted">尚未启动过解析任务。</p>}
        <table className="character-table">
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_id}>
                <td>
                  <Link className="character-link" to={`/jobs/${job.job_id}`}>
                    <span className="numeric">{job.job_id}</span>
                  </Link>
                </td>
                <td>
                  <span className={`badge badge-job-${job.status}`}>{job.status}</span>
                  {job.cancel_requested && <span className="badge badge-review">取消请求中</span>}
                </td>
                <td className="numeric small">
                  {job.stages.filter((stage) => stage.status === "succeeded").length}/{job.stages.length} 阶段
                </td>
                <td className="small">{job.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pane">
        <div className="pane-header">
          <h2>稳定人物索引（subjects）</h2>
        </div>
        {subjects.length === 0 && (
          <p className="muted">解析发布后，run 内的人物会以稳定 subject_id 登记在此，跨 run 保持同一身份。</p>
        )}
        <ul className="subject-list">
          {subjects.map((subject) => (
            <li key={subject.subject_id} className="subject-card">
              <span className="subject-label">{subject.preferred_label}</span>
              <span className="numeric small">{subject.subject_id}</span>
              <span className={`badge badge-job-${subject.status}`}>{subject.status}</span>
              <span className="subject-mappings">
                {subject.run_mappings.map((mapping) => (
                  <Link key={`${mapping.run_id}:${mapping.character_id}`} to={`/runs/${mapping.run_id}`} className="small">
                    {mapping.run_id}
                  </Link>
                ))}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

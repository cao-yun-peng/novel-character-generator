import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { JobEvent, JobRecord } from "../api/types";

const TERMINAL_JOB_STATUSES = new Set(["succeeded", "partial", "failed", "cancelled"]);
const ACTIVE_JOB_STATUSES = new Set(["queued", "running"]);
const POLL_INTERVAL_MS = 1500;

export default function JobDetailPage() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<JobRecord | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const cursorRef = useRef(0);
  const settledRef = useRef(false);

  useEffect(() => {
    cursorRef.current = 0;
    settledRef.current = false;
    setEvents([]);
    setJob(null);
    setError(null);

    let cancelled = false;

    const poll = async () => {
      try {
        const detail = await api.getJob(jobId);
        const eventsPayload = await api.getJobEvents(jobId, cursorRef.current);
        if (cancelled) return;
        setJob(detail.job);
        if (eventsPayload.events.length > 0) {
          setEvents((previous) => [...previous, ...eventsPayload.events]);
          cursorRef.current = eventsPayload.next_cursor;
        }
        if (TERMINAL_JOB_STATUSES.has(detail.job.status)) {
          settledRef.current = true;
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
      }
    };

    const handle = setInterval(() => {
      if (!settledRef.current) void poll();
    }, POLL_INTERVAL_MS);
    void poll();
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [jobId]);

  const act = async (action: "cancel" | "resume") => {
    setActing(true);
    setError(null);
    settledRef.current = false;
    try {
      const payload = action === "cancel" ? await api.cancelJob(jobId) : await api.resumeJob(jobId);
      setJob(payload.job);
      if (action === "resume") {
        cursorRef.current = 0;
        setEvents([]);
      }
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setActing(false);
    }
  };

  if (!job) {
    return (
      <section className="page">
        <h1>解析任务</h1>
        {error ? <div className="error-box">{error}</div> : <p>加载中…</p>}
      </section>
    );
  }

  const statusBadge = <span className={`badge badge-job-${job.status}`}>{job.status}</span>;

  return (
    <section className="page">
      <div className="detail-header">
        <Link className="back-link" to={`/documents/${job.document_id}`}>
          ← {job.display_name}
        </Link>
      </div>
      <h1>
        任务 <span className="numeric">{job.job_id}</span> {statusBadge}
      </h1>
      <p className="page-hint">
        目标 run <span className="numeric">{job.run_id}</span> · 来源版本{" "}
        <span className="numeric">{job.source_document_version_id}</span> · chunk {job.pipeline.chunk_size} / overlap{" "}
        {job.pipeline.overlap_characters}
      </p>

      {job.cancel_requested && ACTIVE_JOB_STATUSES.has(job.status) && (
        <div className="warn-box">已请求取消：正在等待当前阶段在安全边界停下，已发出的模型请求可能继续结束。</div>
      )}
      {job.status === "partial" && (
        <div className="warn-box">
          流水线部分完成（{job.error}）。部分完成的阶段产物保留在任务目录中，可通过“继续执行”从断点恢复。
        </div>
      )}
      {job.status === "failed" && <div className="error-box">{job.error ?? "任务失败"}</div>}
      {error && <div className="error-box">{error}</div>}

      <div className="form-actions">
        {ACTIVE_JOB_STATUSES.has(job.status) && !job.cancel_requested && (
          <button className="button" disabled={acting} onClick={() => act("cancel")}>
            请求取消
          </button>
        )}
        {["cancelled", "partial", "failed"].includes(job.status) && (
          <button className="button" disabled={acting} onClick={() => act("resume")}>
            继续执行（断点恢复）
          </button>
        )}
        {job.status === "succeeded" && (
          <Link className="button" to={`/runs/${job.run_id}`}>
            查看运行结果：{job.run_id}
          </Link>
        )}
      </div>

      <div className="pane">
        <div className="pane-header">
          <h2>阶段进度</h2>
        </div>
        <table className="character-table stage-table">
          <thead>
            <tr>
              <th>阶段</th>
              <th>状态</th>
              <th>进度</th>
              <th>模型调用</th>
              <th>错误</th>
            </tr>
          </thead>
          <tbody>
            {job.stages.map((stage) => (
              <tr key={stage.stage_id}>
                <td>
                  {stage.name}
                  <span className="muted small"> · {stage.stage_id}</span>
                </td>
                <td>
                  <span className={`badge badge-stage-${stage.status}`}>{stage.status}</span>
                </td>
                <td className="numeric">
                  {stage.progress.total != null ? `${stage.progress.done}/${stage.progress.total}` : "—"}
                </td>
                <td className="numeric">{stage.provider_calls || "—"}</td>
                <td className="small stage-error">{stage.error ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pane">
        <div className="pane-header">
          <h2>事件流（增量游标 {cursorRef.current}）</h2>
        </div>
        <ul className="event-log">
          {[...events].reverse().map((event) => (
            <li key={event.seq} className="event-item">
              <span className="numeric small">#{event.seq}</span>
              <span className={`event-type event-type-${event.type}`}>{event.type}</span>
              {event.stage_id && <span className="muted small">{event.stage_id}</span>}
              {event.message && <span className="small event-message">{event.message}</span>}
            </li>
          ))}
          {events.length === 0 && <li className="muted small">暂无事件。</li>}
        </ul>
      </div>
    </section>
  );
}

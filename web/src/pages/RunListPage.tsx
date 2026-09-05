import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { RunSummary } from "../api/types";

export default function RunListPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listRuns()
      .then((payload) => setRuns(payload.runs))
      .catch((e: unknown) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="page">
      <h1>运行结果集</h1>
      <p className="page-hint">每个运行结果集绑定一组经哈希校验的不可变产物；页面显式选择，不自动混用。</p>
      {loading && <p>加载中…</p>}
      {error && <div className="error-box">{error}</div>}
      <ul className="run-list">
        {runs.map((run) => (
          <li key={run.run_id} className="run-card">
            <Link to={`/runs/${run.run_id}`} className="run-link">
              <div className="run-name">{run.display_name}</div>
              <div className="run-meta">
                <span>{run.run_id}</span>
                <span>来源版本 {run.source_document_version_id}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

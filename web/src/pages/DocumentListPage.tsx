import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { DocumentSummary } from "../api/types";

export default function DocumentListPage() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listDocuments()
      .then((payload) => setDocuments(payload.documents))
      .catch((e: unknown) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="page">
      <h1>文档库</h1>
      <p className="page-hint">每个文档按内容寻址，可拥有多个不可变来源版本；解析任务从指定版本启动。</p>
      {loading && <p>加载中…</p>}
      {error && <div className="error-box">{error}</div>}
      <div className="page-header-row">
        <Link className="button" to="/import">
          导入新文档
        </Link>
      </div>
      <ul className="document-list">
        {documents.map((document) => (
          <li key={document.document_id} className="document-card">
            <Link to={`/documents/${document.document_id}`} className="document-link">
              <div className="run-name">{document.display_name}</div>
              <div className="run-meta">
                <span className="numeric">{document.document_id}</span>
                <span>{document.versions.length} 个版本</span>
                {document.latest_version_id && <span>最新 {document.latest_version_id}</span>}
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {!loading && documents.length === 0 && (
        <p className="muted">还没有文档。先导入一篇小说原文，或回到运行结果集浏览既有产物。</p>
      )}
    </section>
  );
}

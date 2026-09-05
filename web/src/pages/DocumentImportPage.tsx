import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { DocumentUploadResponse } from "../api/types";

export default function DocumentImportPage() {
  const [displayName, setDisplayName] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DocumentUploadResponse | null>(null);

  const codePoints = Array.from(text).length;

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    const content = await file.text();
    setText(content);
    if (!displayName.trim()) setDisplayName(file.name.replace(/\.txt$/i, ""));
  };

  const submit = async () => {
    if (!text.trim()) {
      setError("正文不能为空");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload = await api.uploadDocument(displayName.trim(), text);
      setResult(payload);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <section className="page">
        <h1>导入完成</h1>
        <div className="pane">
          <div className="pane-header">
            <h2>{result.display_name}</h2>
          </div>
          <div className="form-field">
            <span className="muted">文档 ID</span>
            <span className="numeric">{result.document_id}</span>
          </div>
          <div className="form-field">
            <span className="muted">来源版本</span>
            <span className="numeric">{result.version.version_id}</span>
            <span className="muted small">{result.version.code_points} code points</span>
          </div>
          {!result.created && (
            <div className="warn-box small">内容已存在：返回了既有文档与版本的不可变绑定。</div>
          )}
          <div className="form-actions">
            <Link className="button" to={`/documents/${result.document_id}`}>
              前往文档，启动解析
            </Link>
            <button
              className="link-button"
              onClick={() => {
                setResult(null);
                setText("");
                setDisplayName("");
              }}
            >
              再导入一篇
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="page">
      <h1>导入小说原文</h1>
      <p className="page-hint">
        原文按内容寻址存储：相同正文返回同一版本，不做任何改写；换行与编码原样保留（CRLF 保真）。
      </p>
      {error && <div className="error-box">{error}</div>}
      <div className="pane import-form">
        <div className="form-field">
          <label htmlFor="display-name">显示名称（可选）</label>
          <input
            id="display-name"
            value={displayName}
            placeholder="例如：斗罗大陆·前20章"
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </div>
        <div className="form-field">
          <label htmlFor="file-picker">或选择本地 .txt 文件</label>
          <input
            id="file-picker"
            type="file"
            accept=".txt,text/plain"
            onChange={(event) => onFile(event.target.files?.[0])}
          />
        </div>
        <div className="form-field">
          <label htmlFor="raw-text">正文（粘贴或由文件载入）</label>
          <textarea
            id="raw-text"
            value={text}
            rows={14}
            placeholder="粘贴小说原文…"
            onChange={(event) => setText(event.target.value)}
          />
          <span className="muted small">{codePoints} code points（上限 5,000,000）</span>
        </div>
        <div className="form-actions">
          <button className="button" disabled={busy || !text.trim()} onClick={submit}>
            {busy ? "上传中…" : "建立不可变版本"}
          </button>
        </div>
      </div>
    </section>
  );
}

import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api/client";
import type { TextWindowResponse } from "../api/types";
import { buildOffsetMap, mergeHighlights, spanToUtf16, type Span } from "../lib/offsets";

export type HighlightKind = "active" | "provisional" | "transition" | "selected";

export interface TextHighlight {
  span: Span;
  kind: HighlightKind;
  title: string;
}

interface Props {
  runId: string;
  windowStart: number;
  windowEnd: number;
  highlights: TextHighlight[];
}

interface Segment {
  text: string;
  kind: HighlightKind | null;
  title: string | null;
}

const KIND_PRIORITY: Record<HighlightKind, number> = { selected: 3, active: 2, provisional: 1, transition: 0 };

export default function TextPane({ runId, windowStart, windowEnd, highlights }: Props) {
  const [textWindow, setTextWindow] = useState<TextWindowResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getTextWindow(runId, windowStart, windowEnd)
      .then(setTextWindow)
      .catch((e: unknown) => setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)))
      .finally(() => setLoading(false));
  }, [runId, windowStart, windowEnd]);

  const segments = useMemo<Segment[]>(() => {
    if (!textWindow) return [];
    const map = buildOffsetMap(textWindow.text, textWindow.start);
    const inWindow = highlights
      .map((h) => ({ ...h, range: spanToUtf16(map, h.span) }))
      .filter((h): h is { span: Span; kind: HighlightKind; title: string; range: { start: number; end: number } } =>
        h.range !== null,
      );
    const merged = mergeHighlights(inWindow.map((h) => ({ start: h.range.start, end: h.range.end })));
    const result: Segment[] = [];
    let cursor = 0;
    for (const piece of merged) {
      if (piece.start > cursor) {
        result.push({ text: textWindow.text.slice(cursor, piece.start), kind: null, title: null });
      }
      const owners = inWindow.filter((h) => h.range.start < piece.end && h.range.end > piece.start);
      owners.sort((a, b) => KIND_PRIORITY[b.kind] - KIND_PRIORITY[a.kind]);
      result.push({
        text: textWindow.text.slice(piece.start, piece.end),
        kind: owners[0]?.kind ?? null,
        title: owners.map((o) => o.title).join(" / ") || null,
      });
      cursor = piece.end;
    }
    if (cursor < textWindow.text.length) {
      result.push({ text: textWindow.text.slice(cursor), kind: null, title: null });
    }
    return result;
  }, [textWindow, highlights]);

  return (
    <div className="pane text-pane">
      <div className="pane-header">
        <h2>原文窗口</h2>
        {textWindow && (
          <span className="muted small">
            code point [{textWindow.start}, {textWindow.end}) / 共 {textWindow.total_code_points}
          </span>
        )}
      </div>
      {error && <div className="error-box">{error}</div>}
      {loading && !textWindow && <p>加载中…</p>}
      {textWindow && (
        <pre className="source-text">
          {segments.map((segment, index) =>
            segment.kind ? (
              <span key={index} className={`hl hl-${segment.kind}`} title={segment.title ?? undefined}>
                {segment.text}
              </span>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </pre>
      )}
    </div>
  );
}

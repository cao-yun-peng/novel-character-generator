/**
 * Code point <-> UTF-16 index mapping (R10 coordinate contract).
 *
 * Backend spans use unicode_codepoint offsets over the raw source text.
 * JavaScript strings are UTF-16, so browser code must never slice a
 * backend span directly: build an OffsetMap for the loaded window and
 * convert code point offsets to UTF-16 indices first.
 */

export interface Span {
  start: number;
  end: number;
}

export interface OffsetMap {
  /** offsets[i] = UTF-16 index of code point i within the window text; length = codePointCount + 1 */
  readonly offsets: Uint32Array;
  readonly codePointCount: number;
  /** code point offset of the window's first character within the whole document */
  readonly windowStart: number;
}

export function buildOffsetMap(text: string, windowStart = 0): OffsetMap {
  const offsets = new Uint32Array(text.length + 1);
  let cp = 0;
  let u16 = 0;
  while (u16 < text.length) {
    offsets[cp] = u16;
    const code = text.codePointAt(u16)!;
    u16 += code > 0xffff ? 2 : 1;
    cp += 1;
  }
  offsets[cp] = text.length;
  return { offsets: offsets.subarray(0, cp + 1), codePointCount: cp, windowStart };
}

/** Document-level code point index -> UTF-16 index inside the window text; -1 if outside. */
export function codePointToUtf16(map: OffsetMap, documentCpIndex: number): number {
  const local = documentCpIndex - map.windowStart;
  if (local < 0 || local > map.codePointCount) return -1;
  return map.offsets[local];
}

/** Clamp a document-level span to the window and convert to UTF-16 indices; null if fully outside. */
export function spanToUtf16(map: OffsetMap, span: Span): { start: number; end: number } | null {
  const localStart = Math.max(span.start - map.windowStart, 0);
  const localEnd = Math.min(span.end - map.windowStart, map.codePointCount);
  if (localStart >= localEnd) return null;
  return { start: map.offsets[localStart], end: map.offsets[localEnd] };
}

/** Code point slicing with Python semantics (half-open range). */
export function sliceByCodePoint(text: string, startCp: number, endCp: number): string {
  const cps = Array.from(text);
  return cps.slice(startCp, endCp).join("");
}

/** Code point length of a string. */
export function codePointLength(text: string): number {
  let count = 0;
  for (let u16 = 0; u16 < text.length; ) {
    const code = text.codePointAt(u16)!;
    u16 += code > 0xffff ? 2 : 1;
    count += 1;
  }
  return count;
}

/** Segment overlapping spans in document code point space into non-crossing render ranges. */
export function mergeHighlights(spans: Span[]): Span[] {
  const sorted = [...spans].sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: Span[] = [];
  for (const span of sorted) {
    const last = merged[merged.length - 1];
    if (last && span.start <= last.end) {
      last.end = Math.max(last.end, span.end);
    } else {
      merged.push({ ...span });
    }
  }
  return merged;
}

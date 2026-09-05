import { describe, expect, it } from "vitest";
import {
  buildOffsetMap,
  codePointLength,
  codePointToUtf16,
  mergeHighlights,
  sliceByCodePoint,
  spanToUtf16,
} from "./offsets";

// Shared corpus: mirrors the backend synthetic document in tests/test_webapp.py.
const CORPUS =
  "第一段：唐三穿着一身灰衣。\r\n" +
  "第二段：他开心地笑了😀一下。\r\n" +
  "第三段：𠮷是一个扩展区汉字。\n" +
  "第四段：cafe\u0301 上有组合字符。\n" +
  "重复引文：一身灰衣。又见一身灰衣。\n";

/** Code point index of the first occurrence of needle (String.indexOf returns UTF-16 indices). */
function cpIndex(text: string, needle: string, fromCp = 0): number {
  let cp = 0;
  let u16 = 0;
  while (u16 < text.length) {
    if (cp >= fromCp && text.startsWith(needle, u16)) return cp;
    const code = text.codePointAt(u16)!;
    u16 += code > 0xffff ? 2 : 1;
    cp += 1;
  }
  return -1;
}

describe("code point <-> UTF-16 mapping", () => {
  it("identity mapping for pure BMP text", () => {
    const text = "唐三穿着一身灰衣";
    const map = buildOffsetMap(text);
    expect(map.codePointCount).toBe(text.length);
    for (let i = 0; i <= text.length; i += 1) {
      expect(codePointToUtf16(map, i)).toBe(i);
    }
  });

  it("counts supplementary plane characters as one code point", () => {
    expect(codePointLength("😀")).toBe(1);
    expect(codePointLength("𠮷")).toBe(1);
    expect("😀".length).toBe(2);
    expect("𠮷".length).toBe(2);
    const hanziCp = cpIndex(CORPUS, "𠮷");
    expect(hanziCp).toBeGreaterThan(0);
    const emojiOccurrences = CORPUS.split("😀").length - 1;
    const hanziOccurrences = CORPUS.split("𠮷").length - 1;
    expect(codePointLength(CORPUS)).toBe(CORPUS.length - emojiOccurrences - hanziOccurrences);
  });

  it("maps document code point offsets to UTF-16 indices across surrogate pairs", () => {
    const map = buildOffsetMap(CORPUS);
    const emojiCp = cpIndex(CORPUS, "😀");
    expect(codePointToUtf16(map, emojiCp)).toBe(CORPUS.indexOf("😀"));
    expect(codePointToUtf16(map, emojiCp + 1)).toBe(CORPUS.indexOf("😀") + 2);

    const hanziCp = cpIndex(CORPUS, "𠮷");
    const hanziU16 = CORPUS.indexOf("𠮷");
    expect(hanziU16 - hanziCp).toBe(1); // one surrogate pair before it
    expect(codePointToUtf16(map, hanziCp)).toBe(hanziU16);
    expect(codePointToUtf16(map, hanziCp + 1)).toBe(hanziU16 + 2);
    expect(sliceByCodePoint(CORPUS, hanziCp, hanziCp + 1)).toBe("𠮷");
  });

  it("combining marks and CRLF each stay two code points", () => {
    const combiningCp = cpIndex(CORPUS, "e\u0301");
    expect(sliceByCodePoint(CORPUS, combiningCp, combiningCp + 2)).toBe("e\u0301");
    const crlfCp = cpIndex(CORPUS, "\r\n");
    expect(sliceByCodePoint(CORPUS, crlfCp, crlfCp + 2)).toBe("\r\n");
  });

  it("slices by code point with Python half-open semantics", () => {
    expect(sliceByCodePoint("a😀b", 1, 2)).toBe("😀");
    expect(sliceByCodePoint("a😀b", 0, 3)).toBe("a😀b");
    expect(sliceByCodePoint("𠮷x", 1, 2)).toBe("x");
  });

  it("round-trips against Python-style windows", () => {
    // The backend returns text[start:end] sliced by code points; the same
    // slice reproduced locally must match byte-for-byte.
    for (const [start, end] of [[0, 20], [15, 32], [35, 50]] as const) {
      const sliced = sliceByCodePoint(CORPUS, start, end);
      const window = { text: sliced, windowStart: start };
      const map = buildOffsetMap(window.text, window.windowStart);
      expect(map.codePointCount).toBe(end - start);
      expect(codePointToUtf16(map, start)).toBe(0);
    }
  });
});

describe("windowed span conversion", () => {
  it("returns null for spans outside the window", () => {
    const map = buildOffsetMap(CORPUS.slice(0, 30), 0);
    expect(spanToUtf16(map, { start: 100, end: 200 })).toBeNull();
  });

  it("clamps spans crossing the window boundary", () => {
    const map = buildOffsetMap(CORPUS.slice(0, 30), 0);
    const result = spanToUtf16(map, { start: 25, end: 60 });
    expect(result).not.toBeNull();
    expect(result!.end - result!.start).toBeGreaterThan(0);
  });

  it("locates duplicate quotes by span, never by string search", () => {
    const map = buildOffsetMap(CORPUS, 0);
    const firstCp = cpIndex(CORPUS, "一身灰衣");
    const secondCp = cpIndex(CORPUS, "一身灰衣", firstCp + 1);
    expect(firstCp).toBeGreaterThan(-1);
    expect(secondCp).toBeGreaterThan(firstCp);
    const a = spanToUtf16(map, { start: firstCp, end: firstCp + 4 });
    const b = spanToUtf16(map, { start: secondCp, end: secondCp + 4 });
    expect(a).not.toBeNull();
    expect(b).not.toBeNull();
    expect(CORPUS.slice(a!.start, a!.end)).toBe("一身灰衣");
    expect(CORPUS.slice(b!.start, b!.end)).toBe("一身灰衣");
    expect(a!.start).not.toBe(b!.start);
  });
});

describe("mergeHighlights", () => {
  it("merges overlapping and adjacent spans", () => {
    expect(mergeHighlights([{ start: 0, end: 5 }, { start: 3, end: 8 }])).toEqual([{ start: 0, end: 8 }]);
    expect(mergeHighlights([{ start: 10, end: 12 }, { start: 0, end: 3 }])).toEqual([
      { start: 0, end: 3 },
      { start: 10, end: 12 },
    ]);
  });
});

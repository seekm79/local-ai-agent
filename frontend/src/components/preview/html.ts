// Detect a full HTML document in an assistant message so we can offer a
// "Preview" button. Looks inside fenced code blocks first, then the raw text.
const HTML_RE = /<!doctype html|<html[\s>]/i;

export function extractHtmlDoc(content: string): string | null {
  const blocks = [...content.matchAll(/```[a-zA-Z]*\n([\s\S]*?)```/g)].map(
    (m) => m[1],
  );
  for (const b of blocks) {
    if (HTML_RE.test(b)) return b.trim();
  }
  if (HTML_RE.test(content)) return content.trim();
  return null;
}

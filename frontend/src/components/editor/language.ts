// Map a file path to a Monaco language id (auto-detect for the editor).
const EXT_TO_LANG: Record<string, string> = {
  cs: "csharp",
  dart: "dart",
  gd: "plaintext", // GDScript has no built-in Monaco grammar
  tsx: "typescript",
  ts: "typescript",
  jsx: "javascript",
  js: "javascript",
  html: "html",
  css: "css",
  json: "json",
  md: "markdown",
  yaml: "yaml",
  yml: "yaml",
  py: "python",
  sh: "shell",
  xml: "xml",
};

export function languageFor(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return EXT_TO_LANG[ext] ?? "plaintext";
}

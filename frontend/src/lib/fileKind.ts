// Classify a file path for the viewer: media kinds render natively (via the
// backend's /raw endpoint, which supports Range for video seeking), "doc" is
// server-extracted text shown read-only, everything else opens in Monaco.
export type FileKind = "image" | "video" | "audio" | "pdf" | "doc" | "code";

const IMAGE = new Set(["png", "jpg", "jpeg", "webp", "gif", "svg", "ico", "bmp", "avif"]);
const VIDEO = new Set(["mp4", "webm", "mov", "m4v", "ogv"]);
const AUDIO = new Set(["mp3", "wav", "ogg", "m4a", "flac", "aac"]);
const DOC = new Set(["doc", "docx"]);

export function fileKind(path: string): FileKind {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (IMAGE.has(ext)) return "image";
  if (VIDEO.has(ext)) return "video";
  if (AUDIO.has(ext)) return "audio";
  if (ext === "pdf") return "pdf";
  if (DOC.has(ext)) return "doc";
  return "code";
}

/** Kinds whose bytes are streamed from /raw — no text fetch on open. */
export const isRawMedia = (k: FileKind) =>
  k === "image" || k === "video" || k === "audio" || k === "pdf";

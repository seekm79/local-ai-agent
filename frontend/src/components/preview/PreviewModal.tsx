import { useEffect } from "react";
import { DiffEditor } from "@monaco-editor/react";
import { usePreview } from "../../stores/preview";
import { languageFor } from "../editor/language";

// Global preview modal. HTML is rendered in a sandboxed iframe (allow-scripts,
// NO allow-same-origin — Phase 5 security requirement); dev-server URLs load in
// a plain iframe; images/videos render directly (video supports seeking via the
// backend's range-capable raw route).
export default function PreviewModal() {
  const { content, close } = usePreview();

  useEffect(() => {
    if (!content) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [content, close]);

  if (!content) return null;

  const title =
    content.title ??
    (content.kind === "html"
      ? "HTML preview"
      : content.kind === "url"
        ? content.url
        : content.kind === "image"
          ? "Image"
          : content.kind === "diff"
            ? content.path
            : "Video");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      onClick={close}
    >
      <div
        className="flex h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-edge bg-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-edge px-4 py-2">
          <span className="truncate text-sm text-neutral-300">{title}</span>
          <div className="flex items-center gap-2">
            {content.kind === "url" && (
              <a
                href={content.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-accent hover:underline"
              >
                open in tab ↗
              </a>
            )}
            <button
              className="text-neutral-400 hover:text-white"
              onClick={close}
              title="Close (Esc)"
            >
              ✕
            </button>
          </div>
        </header>

        <div className="flex min-h-0 flex-1 items-center justify-center bg-black/30">
          {content.kind === "html" && (
            <iframe
              title="html-preview"
              sandbox="allow-scripts"
              srcDoc={content.html}
              className="h-full w-full border-0 bg-white"
            />
          )}
          {content.kind === "url" && (
            <iframe
              title="url-preview"
              src={content.url}
              className="h-full w-full border-0 bg-white"
            />
          )}
          {content.kind === "image" && (
            <img
              src={content.src}
              alt={title}
              className="max-h-full max-w-full object-contain"
            />
          )}
          {content.kind === "video" && (
            <video
              src={content.src}
              controls
              autoPlay
              className="max-h-full max-w-full"
            />
          )}
          {content.kind === "diff" && (
            <DiffEditor
              height="100%"
              theme="vs-dark"
              language={languageFor(content.path)}
              original={content.before}
              modified={content.after}
              options={{
                readOnly: true,
                renderSideBySide: true,
                automaticLayout: true,
                minimap: { enabled: false },
                fontSize: 13,
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

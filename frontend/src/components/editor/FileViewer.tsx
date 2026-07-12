import { rawUrl } from "../../api/client";
import { fileKind } from "../../lib/fileKind";
import CodeEditor from "./CodeEditor";

// Renders one open file by kind: images/video/audio/PDF stream from the /raw
// endpoint, Word docs show their server-extracted text read-only, and
// everything else gets the Monaco editor.
export default function FileViewer({
  projectId,
  path,
  content,
}: {
  projectId: number;
  path: string;
  content: string;
}) {
  const kind = fileKind(path);
  const src = rawUrl(projectId, path);

  switch (kind) {
    case "image":
      return (
        <div className="flex h-full items-center justify-center overflow-auto bg-[#101014] p-4">
          <img
            src={src}
            alt={path}
            className="max-h-full max-w-full rounded border border-edge object-contain"
          />
        </div>
      );
    case "video":
      return (
        <div className="flex h-full items-center justify-center bg-[#101014] p-4">
          <video
            src={src}
            controls
            loop
            className="max-h-full max-w-full rounded border border-edge"
          />
        </div>
      );
    case "audio":
      return (
        <div className="flex h-full items-center justify-center bg-[#101014] p-4">
          <audio src={src} controls className="w-2/3" />
        </div>
      );
    case "pdf":
      // Browser's built-in PDF viewer; same-origin so no CSP issues.
      return <iframe src={src} title={path} className="h-full w-full border-0" />;
    case "doc":
      return (
        <div className="h-full overflow-auto p-4">
          <div className="mb-2 text-xs text-neutral-500">
            Extracted text (read-only) — Word documents can’t be edited here.
          </div>
          <pre className="whitespace-pre-wrap text-sm text-neutral-200">
            {content || "(no extractable text)"}
          </pre>
        </div>
      );
    default:
      return <CodeEditor path={path} content={content} />;
  }
}

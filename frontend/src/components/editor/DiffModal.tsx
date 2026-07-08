import { DiffEditor } from "@monaco-editor/react";
import { languageFor } from "./language";

// Shows Monaco's side-by-side diff of the current file vs. proposed content
// before the user commits an "apply to editor".
export default function DiffModal({
  path,
  original,
  modified,
  onApply,
  onClose,
}: {
  path: string;
  original: string;
  modified: string;
  onApply: () => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-8">
      <div className="flex h-[80vh] w-full max-w-6xl flex-col rounded-lg border border-edge bg-panel">
        <header className="flex items-center justify-between border-b border-edge px-4 py-2">
          <span className="text-sm">
            Apply changes to <code className="text-accent">{path}</code>
          </span>
          <button className="text-neutral-400 hover:text-white" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="min-h-0 flex-1">
          <DiffEditor
            height="100%"
            theme="vs-dark"
            language={languageFor(path)}
            original={original}
            modified={modified}
            options={{
              readOnly: true,
              renderSideBySide: true,
              automaticLayout: true,
              minimap: { enabled: false },
              fontSize: 13,
            }}
          />
        </div>
        <footer className="flex justify-end gap-2 border-t border-edge px-4 py-2 text-sm">
          <button className="rounded px-3 py-1 hover:bg-edge" onClick={onClose}>
            Cancel
          </button>
          <button
            className="rounded bg-accent px-3 py-1 font-medium text-black"
            onClick={onApply}
          >
            Apply & save
          </button>
        </footer>
      </div>
    </div>
  );
}

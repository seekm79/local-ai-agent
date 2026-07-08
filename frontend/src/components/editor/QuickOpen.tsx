import { useEffect, useMemo, useState } from "react";
import * as api from "../../api/client";
import { useProject } from "../../stores/project";

// Cmd/Ctrl+P file quick-open palette for the active project.
export default function QuickOpen({
  projectId,
  onClose,
}: {
  projectId: number;
  onClose: () => void;
}) {
  const openFile = useProject((s) => s.openFile);
  const [files, setFiles] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);

  useEffect(() => {
    void api.allFiles(projectId).then(setFiles).catch(() => setFiles([]));
  }, [projectId]);

  const matches = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = needle
      ? files.filter((f) => f.toLowerCase().includes(needle))
      : files;
    return list.slice(0, 50);
  }, [files, q]);

  useEffect(() => setSel(0), [q]);

  const choose = (path: string) => {
    void openFile(path);
    onClose();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") return onClose();
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSel((s) => Math.min(s + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSel((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter" && matches[sel]) {
      e.preventDefault();
      choose(matches[sel]);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-24"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-lg border border-edge bg-panel shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          autoFocus
          className="w-full border-b border-edge bg-panelalt px-3 py-2 text-sm outline-none"
          placeholder="Quick open — type to filter files…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
        />
        <ul className="max-h-80 overflow-y-auto py-1 text-sm">
          {matches.length === 0 && (
            <li className="px-3 py-2 text-neutral-500">No matching files.</li>
          )}
          {matches.map((f, i) => (
            <li key={f}>
              <button
                className={
                  "flex w-full items-center gap-2 px-3 py-1 text-left " +
                  (i === sel ? "bg-edge text-neutral-100" : "hover:bg-edge/50")
                }
                onMouseEnter={() => setSel(i)}
                onClick={() => choose(f)}
              >
                <span className="truncate">{f}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

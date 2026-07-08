import { useState } from "react";
import * as api from "../../api/client";
import { useProject } from "../../stores/project";

// Semantic codebase search (8.3): type a query, get the most relevant chunks,
// click to open the file at the matching line.
export default function CodeSearch({ projectId }: { projectId: number }) {
  const openFile = useProject((s) => s.openFile);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<api.SearchHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const run = async () => {
    if (!q.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      const { results } = await api.searchCode(projectId, q.trim());
      setHits(results);
      if (results.length === 0) setNote("No matches (try indexing first).");
    } catch (e) {
      setNote(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-edge px-2 py-1">
        <input
          className="w-full rounded border border-edge bg-panel px-2 py-1 text-xs"
          placeholder="Semantic search… (Enter)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void run()}
        />
        <button
          className="rounded px-1.5 py-1 text-xs hover:bg-edge disabled:opacity-40"
          disabled={busy}
          onClick={() => void run()}
          title="Search"
        >
          🔍
        </button>
      </div>
      <div className="flex-1 overflow-auto py-1 text-xs">
        {busy && <div className="px-2 py-1 text-neutral-500">searching…</div>}
        {note && <div className="px-2 py-1 text-neutral-500">{note}</div>}
        {hits.map((h, i) => (
          <button
            key={i}
            className="flex w-full flex-col gap-0.5 border-b border-edge/40 px-2 py-1 text-left hover:bg-edge/40"
            onClick={() => void openFile(h.path)}
          >
            <div className="flex items-center justify-between">
              <span className="truncate text-accent">{h.path}</span>
              <span className="text-neutral-600">
                :{h.start_line} · {(h.score * 100).toFixed(0)}%
              </span>
            </div>
            <pre className="max-h-16 overflow-hidden whitespace-pre-wrap text-neutral-500">
              {h.text.slice(0, 160)}
            </pre>
          </button>
        ))}
      </div>
    </div>
  );
}

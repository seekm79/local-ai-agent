import { useCallback, useEffect, useState } from "react";
import * as api from "../../api/client";
import { useAgents } from "../../stores/agents";

// Timeline of shadow-git checkpoints for the project, with one-click restore.
export default function CheckpointsPanel({ projectId }: { projectId: number | null }) {
  const liveCheckpoints = useAgents((s) => s.checkpoints);
  const [rows, setRows] = useState<api.CheckpointRow[]>([]);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    if (projectId == null) return setRows([]);
    try {
      setRows(await api.listCheckpoints(projectId));
    } catch {
      setRows([]);
    }
  }, [projectId]);

  useEffect(() => {
    void reload();
  }, [reload, liveCheckpoints.length]); // refresh as the run adds checkpoints

  const restore = async (sha: string, label: string) => {
    if (projectId == null) return;
    if (!confirm(`Restore project to checkpoint "${label}"? Current edits to tracked files are discarded.`))
      return;
    setBusy(true);
    try {
      await api.restoreCheckpoint(projectId, sha);
      await reload();
    } catch (e) {
      alert(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  if (projectId == null) return null;

  return (
    <div className="mt-2 border-t border-edge pt-2">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-xs uppercase tracking-wide text-neutral-500">
          Checkpoints
        </h3>
        <button
          className="text-xs text-neutral-400 hover:text-neutral-200"
          onClick={() =>
            projectId != null &&
            void api
              .snapshotCheckpoint(projectId, "manual checkpoint")
              .then(reload)
          }
        >
          + snapshot
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="px-1 text-xs text-neutral-600">
          None yet — created automatically before each agent code step.
        </p>
      ) : (
        <div className="space-y-1">
          {rows.slice(0, 15).map((c) => (
            <div
              key={c.sha}
              className="flex items-center gap-2 rounded px-1 py-0.5 text-xs"
            >
              <span className="font-mono text-neutral-600">{c.sha.slice(0, 7)}</span>
              <span className="flex-1 truncate text-neutral-300" title={c.label}>
                {c.label}
              </span>
              <button
                disabled={busy}
                className="text-accent hover:underline disabled:opacity-40"
                onClick={() => void restore(c.sha, c.label)}
              >
                restore
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

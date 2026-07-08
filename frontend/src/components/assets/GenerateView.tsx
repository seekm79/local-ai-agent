import { useEffect, useState } from "react";
import type { Workflow } from "../../api/client";
import { useComfy } from "../../stores/comfy";

export default function GenerateView({
  projectId,
  onGenerated,
}: {
  projectId: number | null;
  onGenerated: () => void;
}) {
  const {
    status,
    workflows,
    generating,
    progress,
    lastError,
    savedPaths,
    connect,
    loadStatus,
    loadWorkflows,
    generate,
    setOnDone,
  } = useComfy();

  const [workflowFile, setWorkflowFile] = useState<string>("");
  const [params, setParams] = useState<Record<string, string | number>>({});

  useEffect(() => {
    connect();
    void loadStatus();
    void loadWorkflows();
    setOnDone(onGenerated);
    const t = setInterval(() => void loadStatus(), 8000); // re-check ComfyUI
    return () => clearInterval(t);
  }, [connect, loadStatus, loadWorkflows, setOnDone, onGenerated]);

  const current: Workflow | undefined =
    workflows.find((w) => w.file === workflowFile) ?? workflows[0];

  // Seed form defaults when the selected workflow changes.
  useEffect(() => {
    if (!current) return;
    if (!workflowFile) setWorkflowFile(current.file);
    const seeded: Record<string, string | number> = {};
    for (const s of current.slots) seeded[s.key] = s.default;
    setParams(seeded);
  }, [current, workflowFile]);

  const offline = status && !status.online;

  const onGenerate = () => {
    if (projectId == null || !current) return;
    void generate(projectId, current.file, params);
  };

  return (
    <div className="mx-auto max-w-2xl p-4">
      {/* ComfyUI status */}
      {offline && (
        <div className="mb-4 rounded-lg border border-amber-700 bg-amber-950/30 p-3 text-sm text-amber-200">
          {status?.error ?? "ComfyUI not detected"} — start it at{" "}
          <code>{status?.url}</code> and retry. Generation is disabled until then.
        </div>
      )}
      {status?.online && (
        <div className="mb-4 rounded-lg border border-green-700 bg-green-950/20 p-2 text-sm text-green-300">
          ComfyUI online at <code>{status.url}</code>
        </div>
      )}

      {workflows.length === 0 ? (
        <p className="text-neutral-500">
          No workflow templates found in <code>workflows/</code>.
        </p>
      ) : (
        <>
          <label className="mb-3 block text-xs text-neutral-400">
            Workflow
            <select
              className="mt-1 w-full rounded border border-edge bg-panel px-2 py-1 text-sm text-neutral-200"
              value={current?.file ?? ""}
              onChange={(e) => setWorkflowFile(e.target.value)}
            >
              {workflows.map((w) => (
                <option key={w.file} value={w.file}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>

          {current?.description && (
            <p className="mb-3 text-xs text-neutral-500">{current.description}</p>
          )}

          {/* Parameter form generated from the template's declared slots */}
          <div className="space-y-3">
            {current?.slots.map((s) => (
              <label key={s.key} className="block text-xs text-neutral-400">
                {s.label}
                {s.type === "text" ? (
                  <textarea
                    className="mt-1 w-full resize-none rounded border border-edge bg-panel p-2 text-sm text-neutral-200"
                    rows={2}
                    value={String(params[s.key] ?? "")}
                    onChange={(e) =>
                      setParams((p) => ({ ...p, [s.key]: e.target.value }))
                    }
                  />
                ) : (
                  <input
                    type="number"
                    className="mt-1 w-40 rounded border border-edge bg-panel px-2 py-1 text-sm text-neutral-200"
                    value={String(params[s.key] ?? "")}
                    onChange={(e) =>
                      setParams((p) => ({ ...p, [s.key]: Number(e.target.value) }))
                    }
                  />
                )}
              </label>
            ))}
          </div>

          <button
            className="mt-4 rounded bg-accent px-4 py-2 text-sm font-medium text-black disabled:opacity-40"
            onClick={onGenerate}
            disabled={generating || offline || projectId == null}
          >
            {generating ? "Generating…" : "Generate"}
          </button>

          {/* Live progress */}
          {progress && (
            <div className="mt-4">
              <div className="mb-1 text-xs text-neutral-400">
                Step {progress.value} / {progress.max}
              </div>
              <div className="h-2 w-full overflow-hidden rounded bg-edge">
                <div
                  className="h-full bg-accent transition-all"
                  style={{
                    width: `${Math.round((progress.value / Math.max(1, progress.max)) * 100)}%`,
                  }}
                />
              </div>
            </div>
          )}

          {savedPaths.length > 0 && (
            <div className="mt-4 text-sm text-green-300">
              Saved {savedPaths.length} image(s) to the gallery.
            </div>
          )}
          {lastError && (
            <div className="mt-4 rounded border border-red-800 bg-red-950/30 p-2 text-sm text-red-300">
              {lastError}
            </div>
          )}
        </>
      )}
    </div>
  );
}

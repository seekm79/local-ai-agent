import { useEffect, useState } from "react";
import { useAgents } from "../../stores/agents";
import { useProject } from "../../stores/project";
import { useSession } from "../../stores/session";
import StepCard from "./StepCard";
import CheckpointsPanel from "./CheckpointsPanel";
import ModesModal from "./ModesModal";

export default function AgentsView() {
  const {
    steps,
    status,
    summary,
    goal,
    setGoal,
    start,
    cancel,
    connect,
    runs,
    loadRuns,
    error,
    clearError,
  } = useAgents();
  const { projects, currentId, loadProjects, selectProject } = useProject();
  const { models, model, setModel } = useSession();
  const [modesOpen, setModesOpen] = useState(false);

  useEffect(() => {
    connect();
    void loadProjects();
    void loadRuns();
  }, [connect, loadProjects, loadRuns]);

  const running = status === "running";
  const canStart = !running && currentId != null && goal.trim() && model;

  const maxIterId = "agent-max-iter";

  const onStart = () => {
    if (currentId == null || !model) return;
    const el = document.getElementById(maxIterId) as HTMLInputElement | null;
    const max_iterations = Math.max(1, Number(el?.value) || 3);
    void start({
      project_id: currentId,
      goal: goal.trim(),
      model,
      max_iterations,
    });
  };

  return (
    <div className="flex h-full min-h-0">
      {/* Left: setup + runs history */}
      <aside className="flex w-80 shrink-0 flex-col gap-3 overflow-y-auto border-r border-edge bg-panelalt p-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Agent pipeline</h2>
          <button
            className="rounded px-2 py-1 text-xs text-neutral-400 hover:bg-edge"
            onClick={() => setModesOpen(true)}
          >
            ⚙ Modes
          </button>
        </div>

        <label className="text-xs text-neutral-400">
          Project
          <select
            className="mt-1 w-full rounded border border-edge bg-panel px-2 py-1 text-sm text-neutral-200"
            value={currentId ?? ""}
            onChange={(e) => e.target.value && void selectProject(Number(e.target.value))}
            disabled={running}
          >
            <option value="">— select —</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-neutral-400">
          Model (planner / coder)
          <select
            className="mt-1 w-full rounded border border-edge bg-panel px-2 py-1 text-sm text-neutral-200"
            value={model ?? ""}
            onChange={(e) => setModel(e.target.value)}
            disabled={running || models.length === 0}
          >
            {models.length === 0 && <option value="">no models</option>}
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-neutral-400">
          Goal
          <textarea
            className="mt-1 w-full resize-none rounded border border-edge bg-panel p-2 text-sm"
            rows={4}
            placeholder="e.g. create a C# console app that prints the first 20 Fibonacci numbers and includes a unit test"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            disabled={running}
          />
        </label>

        <label className="flex items-center gap-2 text-xs text-neutral-400">
          Max fix iterations
          <input
            id={maxIterId}
            type="number"
            min={1}
            max={5}
            defaultValue={3}
            className="w-16 rounded border border-edge bg-panel px-2 py-1 text-sm"
            disabled={running}
          />
        </label>

        {running ? (
          <button
            className="rounded bg-red-500 px-3 py-2 text-sm font-medium text-white hover:bg-red-600"
            onClick={() => void cancel()}
          >
            Cancel run
          </button>
        ) : (
          <button
            className="rounded bg-accent px-3 py-2 text-sm font-medium text-black disabled:opacity-40"
            onClick={onStart}
            disabled={!canStart}
          >
            Start run
          </button>
        )}

        <CheckpointsPanel projectId={currentId} />

        <div className="mt-2 border-t border-edge pt-2">
          <h3 className="mb-1 text-xs uppercase tracking-wide text-neutral-500">
            History
          </h3>
          <div className="space-y-1">
            {runs.slice(0, 12).map((r) => (
              <div
                key={r.id}
                className="truncate rounded px-2 py-1 text-xs text-neutral-400"
                title={r.goal}
              >
                <span
                  className={
                    r.status === "done"
                      ? "text-green-400"
                      : r.status === "failed"
                        ? "text-red-400"
                        : "text-neutral-400"
                  }
                >
                  ●
                </span>{" "}
                {r.goal}
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* Right: board */}
      <div className="flex min-h-0 flex-1 flex-col">
        {error && (
          <div className="flex items-center justify-between bg-red-950/60 px-4 py-2 text-sm text-red-200">
            <span>{error}</span>
            <button onClick={clearError}>dismiss</button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="mx-auto max-w-3xl space-y-3">
            {steps.length === 0 && status === "idle" && (
              <div className="mt-16 text-center text-neutral-500">
                Set a project, model, and goal, then start a run. The Planner →
                Coder → Reviewer pipeline will appear here live.
              </div>
            )}
            {status === "running" && steps.length === 0 && (
              <div className="mt-16 text-center text-accent">Planning…</div>
            )}

            {steps.map((s, i) => (
              <StepCard key={s.id} step={s} index={i} />
            ))}

            {summary && (
              <div
                className={
                  "mt-4 rounded-lg border p-4 " +
                  (status === "done"
                    ? "border-green-700 bg-green-950/20"
                    : status === "cancelled"
                      ? "border-neutral-600 bg-panelalt"
                      : "border-amber-700 bg-amber-950/20")
                }
              >
                <div className="mb-1 text-sm font-medium">
                  Run {status} — summary
                </div>
                <pre className="whitespace-pre-wrap text-sm text-neutral-300">
                  {summary}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>

      {modesOpen && <ModesModal onClose={() => setModesOpen(false)} />}
    </div>
  );
}

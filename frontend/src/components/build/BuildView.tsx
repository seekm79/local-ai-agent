import { useEffect, useState } from "react";
import {
  deleteAttachment,
  listAttachments,
  type Attachment,
  type AttachRole,
} from "../../api/client";
import { useBuild } from "../../stores/build";
import { useRun } from "../../stores/run";
import { useAgents } from "../../stores/agents";
import { useSession } from "../../stores/session";
import StepCard from "../agents/StepCard";
import BuildPreview from "./BuildPreview";

const CHIPS = [
  "Habit tracker",
  "SaaS dashboard",
  "Landing page",
  "Kanban board",
];

export default function BuildView() {
  const build = useBuild();
  const { model } = useSession();
  const processes = useRun((s) => s.processes);
  const agents = useAgents();
  const [stopping, setStopping] = useState(false);
  const busy = agents.status === "running" || build.installing;

  // Drive install→dev coordination off run-store updates.
  useEffect(() => {
    build.onProcesses();
  }, [processes, build]);

  useEffect(() => {
    useAgents.getState().connect();
    // After a browser reload, reopen the project that was on screen — steps,
    // Code tab, and live preview all come back.
    void useBuild.getState().restore();
  }, []);

  // Clear the "Stopping…" indicator once the run actually settles.
  useEffect(() => {
    if (!busy) setStopping(false);
  }, [busy]);

  // Pin the agents event stream to the open project so a build running in
  // another project can't take over this view (it keeps going in background).
  useEffect(() => {
    useAgents
      .getState()
      .pinProject(build.phase === "work" ? build.projectId : null);
  }, [build.phase, build.projectId]);

  if (build.phase === "entry") {
    return <EntryScreen />;
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Left: conversation / build feedback */}
      <aside className="flex w-96 shrink-0 flex-col border-r border-edge bg-panelalt">
        <div className="flex items-center gap-2 border-b border-edge px-3 py-2 text-sm">
          <span className="font-medium">{build.projectName}</span>
          {build.installing && (
            <span className="text-xs text-accent">installing deps…</span>
          )}
          {busy && (
            <button
              className="ml-auto flex items-center gap-1 rounded bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-60"
              title="Stop the running build (cancels the AI run and dependency install)"
              disabled={stopping}
              onClick={() => {
                setStopping(true);
                void build.stop();
              }}
            >
              <span className="text-[10px]">■</span> {stopping ? "Stopping…" : "Stop"}
            </button>
          )}
          <button
            className={(busy ? "" : "ml-auto ") + "rounded px-2 py-1 text-xs text-neutral-400 hover:bg-edge"}
            title="Back to your projects — a running build keeps going in the background"
            onClick={() => build.goHome()}
          >
            ← projects
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
          {agents.steps.length === 0 && (
            <div className="mt-8 text-center text-sm text-neutral-500">
              {agents.status === "running" ? "Designing…" : "Waiting for the build to start…"}
            </div>
          )}
          {agents.steps.map((s, i) => (
            <StepCard key={s.id} step={s} index={i} />
          ))}
          {agents.summary && (
            <div className="rounded border border-edge bg-panel p-3 text-sm text-neutral-300">
              {agents.summary}
            </div>
          )}
        </div>

        <FollowUpComposer />
      </aside>

      {/* Right: preview / code / theme */}
      <div className="min-w-0 flex-1">
        <BuildPreview
          projectId={build.projectId!}
          devUrl={build.devUrl}
          model={model ?? undefined}
        />
      </div>
    </div>
  );
}

const roleFor = (file: File): AttachRole =>
  file.type.startsWith("image/") ? "design_reference" : "content";

const RUN_BADGE: Record<string, { label: string; cls: string; pulse?: boolean }> = {
  running: { label: "building…", cls: "text-amber-400", pulse: true },
  pending: { label: "starting…", cls: "text-amber-400", pulse: true },
  done: { label: "✓ done", cls: "text-emerald-400" },
  failed: { label: "✗ failed", cls: "text-red-400" },
  interrupted: { label: "✗ interrupted", cls: "text-red-400" },
  cancelled: { label: "◼ stopped", cls: "text-neutral-500" },
};

function EntryScreen() {
  const build = useBuild();
  const { model } = useSession();
  const agentRuns = useAgents((s) => s.runs);
  const agentStatus = useAgents((s) => s.status);
  const [prompt, setPrompt] = useState("");
  const [attachments, setAttachments] = useState<{ file: File; role: AttachRole }[]>([]);
  const [genImages, setGenImages] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // Keep the recent-builds list (and its running/done badges) current: on
  // mount, and whenever a run starts/finishes anywhere.
  useEffect(() => {
    void build.loadBuildProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentRuns, agentStatus]);

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    setAttachments((a) => [
      ...a,
      ...Array.from(files).map((file) => ({ file, role: roleFor(file) })),
    ]);
  };

  const submit = () => {
    const p = prompt.trim();
    if (!p) return;
    const name = p.split(/\s+/).slice(0, 4).join(" ").slice(0, 40) || "app";
    void build.scaffold(name, p, {
      model: model ?? undefined,
      attachments,
      generateImages: genImages,
    });
  };

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-2xl text-center">
        <h1 className="mb-2 text-3xl font-semibold text-neutral-100">
          Build something
        </h1>
        <p className="mb-6 text-neutral-500">
          Describe an app and Workbench scaffolds it from the base template, then
          designs on top — live preview on the right.
        </p>
        <div
          className={
            "rounded-xl border bg-panel p-3 text-left shadow-lg " +
            (dragOver ? "border-accent" : "border-edge")
          }
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            addFiles(e.dataTransfer.files);
          }}
        >
          <textarea
            className="h-28 w-full resize-none bg-transparent p-2 text-sm outline-none"
            placeholder="Ask Workbench to build something…  e.g. a personal finance dashboard with a warm, editorial look"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
            }}
          />

          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 py-2">
              {attachments.map((a, i) => (
                <span
                  key={i}
                  className="flex items-center gap-1 rounded border border-edge bg-panelalt px-2 py-1 text-xs"
                >
                  <span className="max-w-[8rem] truncate">{a.file.name}</span>
                  <select
                    className="rounded bg-panel text-[10px] text-neutral-300"
                    value={a.role}
                    onChange={(e) =>
                      setAttachments((list) =>
                        list.map((x, j) =>
                          j === i ? { ...x, role: e.target.value as AttachRole } : x,
                        ),
                      )
                    }
                  >
                    <option value="design_reference">design ref</option>
                    <option value="asset">asset</option>
                    <option value="content">content</option>
                  </select>
                  <button
                    className="text-neutral-500 hover:text-red-400"
                    onClick={() =>
                      setAttachments((list) => list.filter((_, j) => j !== i))
                    }
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <label className="cursor-pointer rounded px-2 py-1 text-xs text-neutral-400 hover:bg-edge">
              📎 Attach
              <input
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
            <label className="flex cursor-pointer items-center gap-1 text-xs text-neutral-400">
              <input
                type="checkbox"
                checked={genImages}
                onChange={(e) => setGenImages(e.target.checked)}
              />
              🎨 generate images (ComfyUI)
            </label>
            <span className="ml-auto text-xs text-neutral-600">⌘/Ctrl + Enter</span>
            <button
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-black disabled:opacity-40"
              onClick={submit}
              disabled={!prompt.trim()}
            >
              Build →
            </button>
          </div>
        </div>
        {build.error && (
          <div className="mt-3 rounded border border-red-800 bg-red-950/30 p-2 text-sm text-red-300">
            {build.error}
          </div>
        )}
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {CHIPS.map((c) => (
            <button
              key={c}
              className="rounded-full border border-edge px-3 py-1 text-sm text-neutral-300 hover:bg-edge"
              onClick={() => setPrompt(`Build me a ${c.toLowerCase()}`)}
            >
              {c}
            </button>
          ))}
        </div>

        {build.projects.length > 0 && (
          <div className="mt-8 text-left">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">
              Recent builds
            </div>
            <div className="space-y-1.5">
              {build.projects.map((p) => {
                const badge = p.latest_run
                  ? RUN_BADGE[p.latest_run.status] ?? {
                      label: p.latest_run.status,
                      cls: "text-neutral-500",
                    }
                  : { label: "no runs yet", cls: "text-neutral-600" };
                return (
                  <button
                    key={p.id}
                    className="flex w-full items-center gap-3 rounded-lg border border-edge bg-panel px-3 py-2 text-left hover:border-accent/50 hover:bg-panelalt"
                    onClick={() => void build.openProject(p)}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-neutral-200">
                        {p.name}
                      </span>
                      {p.latest_run && (
                        <span className="block truncate text-xs text-neutral-500">
                          {p.latest_run.goal}
                        </span>
                      )}
                    </span>
                    <span
                      className={`shrink-0 text-xs ${badge.cls} ${badge.pulse ? "animate-pulse" : ""}`}
                    >
                      {badge.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const ROLE_BADGE: Record<string, string> = {
  design_reference: "design ref",
  asset: "asset",
  content: "content",
};

function FollowUpComposer() {
  const build = useBuild();
  const { model } = useSession();
  const running = useAgents((s) => s.status === "running");
  const [text, setText] = useState("");
  const [genImages, setGenImages] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [dragOver, setDragOver] = useState(false);

  const refresh = async () => {
    if (build.projectId == null) return;
    try {
      setAttachments(await listAttachments(build.projectId));
    } catch {
      /* best-effort */
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [build.projectId]);

  const addFiles = async (files: FileList | File[] | null) => {
    if (!files) return;
    for (const f of Array.from(files)) await build.attachToProject(f, roleFor(f));
    void refresh();
  };

  const remove = async (id?: number) => {
    if (id == null || build.projectId == null) return;
    try {
      await deleteAttachment(build.projectId, id);
    } catch {
      /* ignore */
    }
    void refresh();
  };

  const submit = () => {
    const t = text.trim();
    if (!t || running) return;
    setText("");
    void build.followUp(t, { model: model ?? undefined, generateImages: genImages });
  };

  return (
    <div
      className={"border-t p-2 " + (dragOver ? "border-accent bg-accent/5" : "border-edge")}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        void addFiles(e.dataTransfer.files);
      }}
    >
      {attachments.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {attachments.map((a) => (
            <span
              key={a.id ?? a.path}
              className="group flex items-center gap-1 rounded border border-edge bg-panel px-1.5 py-0.5 text-[11px] text-neutral-300"
              title={a.description || a.path}
            >
              {a.kind === "image" ? "🖼" : "📄"}
              <span className="max-w-[9rem] truncate">{a.path.split("/").pop()}</span>
              <span className="text-neutral-500">{ROLE_BADGE[a.role] ?? a.role}</span>
              {a.description && <span title={a.description}>👁</span>}
              <button
                className="text-neutral-500 hover:text-red-400"
                title="Remove attachment"
                onClick={() => void remove(a.id)}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="mb-1 flex items-center gap-3 text-xs text-neutral-400">
        <label className="cursor-pointer rounded px-1.5 py-0.5 hover:bg-edge" title="Attach files (or drag & drop anywhere on this panel)">
          📎 Attach
          <input
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              void addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        <label className="flex cursor-pointer items-center gap-1">
          <input
            type="checkbox"
            checked={genImages}
            onChange={(e) => setGenImages(e.target.checked)}
          />
          🎨 images
        </label>
        {dragOver && <span className="text-accent">drop to attach…</span>}
      </div>
      <div className="flex items-end gap-2">
        <textarea
          className="flex-1 resize-none rounded-md border border-edge bg-panel p-2 text-sm outline-none focus:border-accent"
          rows={2}
          placeholder="Ask for a change… (make the sidebar collapsible, add a settings page)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-black disabled:opacity-40"
          onClick={submit}
          disabled={!text.trim() || running}
        >
          Send
        </button>
      </div>
    </div>
  );
}

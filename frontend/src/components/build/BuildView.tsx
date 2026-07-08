import { useEffect, useState } from "react";
import type { AttachRole } from "../../api/client";
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

  // Drive install→dev coordination off run-store updates.
  useEffect(() => {
    build.onProcesses();
  }, [processes, build]);

  useEffect(() => {
    useAgents.getState().connect();
  }, []);

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
          <button
            className="ml-auto rounded px-2 py-1 text-xs text-neutral-400 hover:bg-edge"
            onClick={() => {
              const running = useAgents.getState().status === "running";
              const msg = running
                ? "A build is still running. Start a new one? This cancels the current build and stops its dev server. Your project files are kept on disk."
                : "Start a new build? This stops the current dev server. Your project files are kept on disk.";
              if (window.confirm(msg)) void build.reset();
            }}
          >
            ← new
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

function EntryScreen() {
  const build = useBuild();
  const { model } = useSession();
  const [prompt, setPrompt] = useState("");
  const [attachments, setAttachments] = useState<{ file: File; role: AttachRole }[]>([]);
  const [genImages, setGenImages] = useState(false);
  const [dragOver, setDragOver] = useState(false);

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
      </div>
    </div>
  );
}

function FollowUpComposer() {
  const build = useBuild();
  const { model } = useSession();
  const running = useAgents((s) => s.status === "running");
  const [text, setText] = useState("");
  const [genImages, setGenImages] = useState(false);

  const submit = () => {
    const t = text.trim();
    if (!t || running) return;
    setText("");
    void build.followUp(t, { model: model ?? undefined, generateImages: genImages });
  };

  return (
    <div className="border-t border-edge p-2">
      <div className="mb-1 flex items-center gap-3 text-xs text-neutral-400">
        <label className="cursor-pointer rounded px-1.5 py-0.5 hover:bg-edge">
          📎
          <input
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              for (const f of Array.from(e.target.files ?? []))
                void build.attachToProject(f, roleFor(f));
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

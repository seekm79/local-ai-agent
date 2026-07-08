import { useEffect, useRef, useState } from "react";
import * as api from "../../api/client";
import { useProject } from "../../stores/project";
import FileTree from "../editor/FileTree";
import EditorTabs from "../editor/EditorTabs";
import CodeEditor from "../editor/CodeEditor";
import ThemePanel from "./ThemePanel";

type Tab = "preview" | "code" | "agents" | "theme";
type Device = "desktop" | "tablet" | "mobile";
const WIDTHS: Record<Device, string> = {
  desktop: "100%",
  tablet: "768px",
  mobile: "375px",
};

export default function BuildPreview({
  projectId,
  devUrl,
  model,
}: {
  projectId: number;
  devUrl: string | null;
  model?: string;
}) {
  const [tab, setTab] = useState<Tab>("preview");
  const [device, setDevice] = useState<Device>("desktop");
  const [nonce, setNonce] = useState(0); // refresh key for the iframe
  const activeFile = useProject((s) =>
    s.openFiles.find((f) => f.path === s.activePath),
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-edge bg-panelalt px-3 py-1.5 text-sm">
        <div className="flex gap-1">
          {(["preview", "code", "agents", "theme"] as Tab[]).map((t) => (
            <button
              key={t}
              className={
                "rounded px-2 py-1 text-xs " +
                (tab === t ? "bg-edge text-neutral-100" : "text-neutral-400 hover:bg-edge/60")
              }
              onClick={() => setTab(t)}
            >
              {t === "agents" ? "AGENTS.md" : t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        {tab === "preview" && (
          <div className="ml-auto flex items-center gap-2 text-xs">
            <div className="flex gap-1">
              {(["desktop", "tablet", "mobile"] as Device[]).map((d) => (
                <button
                  key={d}
                  className={
                    "rounded px-1.5 py-1 " +
                    (device === d ? "bg-edge text-neutral-100" : "text-neutral-400 hover:bg-edge/60")
                  }
                  title={d}
                  onClick={() => setDevice(d)}
                >
                  {d === "desktop" ? "🖥" : d === "tablet" ? "▭" : "▯"}
                </button>
              ))}
            </div>
            <button
              className="rounded px-1.5 py-1 text-neutral-400 hover:bg-edge/60"
              title="Refresh"
              onClick={() => setNonce((n) => n + 1)}
            >
              ↻
            </button>
            {devUrl && (
              <a
                className="rounded px-1.5 py-1 text-neutral-400 hover:bg-edge/60"
                href={devUrl}
                target="_blank"
                rel="noreferrer"
                title="Open in new tab"
              >
                ↗
              </a>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="min-h-0 flex-1">
        {tab === "preview" && (
          <div className="flex h-full items-start justify-center overflow-auto bg-black/20 p-2">
            {devUrl ? (
              <iframe
                key={nonce}
                title="app-preview"
                src={devUrl}
                className="h-full border-0 bg-white"
                style={{ width: WIDTHS[device], maxWidth: "100%" }}
              />
            ) : (
              <div className="mt-24 text-center text-neutral-500">
                <div className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-2 border-edge border-t-accent" />
                Starting the dev server… the preview appears here once it's up.
              </div>
            )}
          </div>
        )}

        {tab === "code" && (
          <div className="flex h-full min-h-0">
            <div className="w-52 shrink-0 border-r border-edge">
              <FileTree />
            </div>
            <div className="flex min-w-0 flex-1 flex-col">
              <EditorTabs />
              <div className="min-h-0 flex-1">
                {activeFile ? (
                  <CodeEditor path={activeFile.path} content={activeFile.content} />
                ) : (
                  <div className="flex h-full items-center justify-center text-neutral-500">
                    Open a file from the tree.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {tab === "agents" && <AgentsMdPanel projectId={projectId} />}
        {tab === "theme" && <ThemePanel projectId={projectId} model={model} />}
      </div>
    </div>
  );
}

function AgentsMdPanel({ projectId }: { projectId: number }) {
  const [content, setContent] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const loaded = useRef(false);

  useEffect(() => {
    loaded.current = false;
    void api
      .readFile(projectId, "AGENTS.md")
      .then((r) => {
        setContent(r.content);
        loaded.current = true;
      })
      .catch(() => setContent("# AGENTS.md not found"));
  }, [projectId]);

  const save = () => {
    void api.writeFile(projectId, "AGENTS.md", content).then(() => setDirty(false));
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-edge px-3 py-1.5 text-xs text-neutral-400">
        <span>📌 The agent reads this first, before every request.</span>
        <button
          className="ml-auto rounded bg-accent px-2 py-1 text-black disabled:opacity-40"
          disabled={!dirty}
          onClick={save}
        >
          Save
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <CodeEditorRaw
          value={content}
          onChange={(v) => {
            setContent(v);
            if (loaded.current) setDirty(true);
          }}
        />
      </div>
    </div>
  );
}

// Small Monaco wrapper for arbitrary text (AGENTS.md).
import Editor from "@monaco-editor/react";
function CodeEditorRaw({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Editor
      height="100%"
      theme="vs-dark"
      language="markdown"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      options={{ fontSize: 13, minimap: { enabled: false }, wordWrap: "on" }}
    />
  );
}

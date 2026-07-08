import { useEffect, useState } from "react";
import { useProject } from "../../stores/project";
import { useSession } from "../../stores/session";
import { ApplyContext } from "../chat/applyContext";
import MessageList from "../chat/MessageList";
import Composer from "../chat/Composer";
import FileTree from "./FileTree";
import CodeSearch from "./CodeSearch";
import EditorTabs from "./EditorTabs";
import CodeEditor from "./CodeEditor";
import DiffModal from "./DiffModal";
import Terminal from "../terminal/Terminal";
import RunPanel from "../terminal/RunPanel";
import ConfirmModal from "../terminal/ConfirmModal";

export default function CodeView() {
  const {
    projects,
    currentId,
    openFiles,
    activePath,
    loadProjects,
    createProject,
    selectProject,
    deleteProject,
    applyToActive,
    saveFile,
    error,
    clearError,
  } = useProject();

  const setCodingContext = useSession((s) => s.setCodingContext);
  const chatError = useSession((s) => s.error);
  const clearChatError = useSession((s) => s.clearError);
  const loadChats = useSession((s) => s.loadChats);

  const [diffCode, setDiffCode] = useState<string | null>(null);
  const [newProjName, setNewProjName] = useState<string | null>(null);
  const [bottomOpen, setBottomOpen] = useState(false);
  const [bottomTab, setBottomTab] = useState<"terminal" | "run">("run");
  const [leftTab, setLeftTab] = useState<"files" | "search">("files");

  // Ctrl+` toggles the terminal/run panel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "`") {
        e.preventDefault();
        setBottomOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    void loadProjects();
    void loadChats();
  }, [loadProjects, loadChats]);

  // Keep the coding chat's file context in sync with the open file.
  useEffect(() => {
    if (currentId != null && activePath)
      setCodingContext({ projectId: currentId, filePath: activePath });
    else setCodingContext(null);
    return () => setCodingContext(null);
  }, [currentId, activePath, setCodingContext]);

  const activeFile = openFiles.find((f) => f.path === activePath) ?? null;

  const onNewProject = () => setNewProjName("");

  const submitNewProject = () => {
    const name = (newProjName ?? "").trim();
    setNewProjName(null);
    if (name) void createProject(name);
  };

  const onDeleteProject = () => {
    if (currentId == null) return;
    const proj = projects.find((p) => p.id === currentId);
    const hard = confirm(
      `Delete project "${proj?.name}"?\n\nOK = also delete files from disk (irreversible).\nCancel = keep, just archive.`,
    );
    void deleteProject(currentId, hard);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Project bar */}
      <div className="flex items-center gap-2 border-b border-edge bg-panelalt px-3 py-1.5 text-sm">
        <span className="text-xs uppercase tracking-wide text-neutral-500">
          Project
        </span>
        <select
          className="rounded border border-edge bg-panel px-2 py-1"
          value={currentId ?? ""}
          onChange={(e) => e.target.value && void selectProject(Number(e.target.value))}
        >
          <option value="">— select —</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        {newProjName === null ? (
          <button className="rounded px-2 py-1 hover:bg-edge" onClick={onNewProject}>
            + New
          </button>
        ) : (
          <input
            autoFocus
            className="rounded border border-edge bg-panel px-2 py-1"
            placeholder="project name"
            value={newProjName}
            onChange={(e) => setNewProjName(e.target.value)}
            onBlur={submitNewProject}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitNewProject();
              if (e.key === "Escape") setNewProjName(null);
            }}
          />
        )}
        {currentId != null && (
          <button
            className="rounded px-2 py-1 text-red-400 hover:bg-edge"
            onClick={onDeleteProject}
          >
            Delete
          </button>
        )}
        {currentId != null && (
          <button
            className={
              "rounded px-2 py-1 " +
              (bottomOpen ? "bg-edge text-neutral-100" : "hover:bg-edge")
            }
            title="Toggle terminal (Ctrl+`)"
            onClick={() => setBottomOpen((v) => !v)}
          >
            Terminal ⌃`
          </button>
        )}
        {(error || chatError) && (
          <span className="ml-auto flex items-center gap-2 text-red-300">
            {error || chatError}
            <button
              className="hover:text-white"
              onClick={() => {
                clearError();
                clearChatError();
              }}
            >
              dismiss
            </button>
          </span>
        )}
      </div>

      {currentId == null ? (
        <div className="flex flex-1 items-center justify-center text-neutral-500">
          <div className="text-center">
            <p>Select or create a project to start coding.</p>
            <button
              className="mt-3 rounded bg-accent px-3 py-1.5 text-sm font-medium text-black"
              onClick={onNewProject}
            >
              + New project
            </button>
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1">
          {/* Left: file tree / semantic search */}
          <div className="flex w-56 shrink-0 flex-col border-r border-edge bg-panelalt">
            <div className="flex border-b border-edge text-xs">
              <button
                className={
                  "flex-1 px-2 py-1 " +
                  (leftTab === "files" ? "bg-edge text-neutral-100" : "text-neutral-400 hover:bg-edge/50")
                }
                onClick={() => setLeftTab("files")}
              >
                Files
              </button>
              <button
                className={
                  "flex-1 px-2 py-1 " +
                  (leftTab === "search" ? "bg-edge text-neutral-100" : "text-neutral-400 hover:bg-edge/50")
                }
                onClick={() => setLeftTab("search")}
              >
                Search
              </button>
            </div>
            <div className="min-h-0 flex-1">
              {leftTab === "files" ? (
                <FileTree />
              ) : (
                <CodeSearch projectId={currentId} />
              )}
            </div>
          </div>

          {/* Center: editor */}
          <div className="flex min-w-0 flex-1 flex-col">
            <EditorTabs />
            <div className="min-h-0 flex-1">
              {activeFile ? (
                <CodeEditor path={activeFile.path} content={activeFile.content} />
              ) : (
                <div className="flex h-full items-center justify-center text-neutral-500">
                  Open a file from the tree to edit it.
                </div>
              )}
            </div>
          </div>

          {/* Right: context-aware chat */}
          <div className="flex w-96 shrink-0 flex-col border-l border-edge">
            <div className="border-b border-edge bg-panelalt px-3 py-1.5 text-xs text-neutral-400">
              Chat{" "}
              {activePath ? (
                <span className="text-accent">· context: {activePath}</span>
              ) : (
                <span className="text-neutral-600">· no file open</span>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
              <ApplyContext.Provider
                value={(code) => {
                  if (activePath) setDiffCode(code);
                }}
              >
                <MessageList />
              </ApplyContext.Provider>
            </div>
            {chatError && (
              <div className="flex items-center justify-between bg-red-950/60 px-3 py-1.5 text-xs text-red-200">
                <span>{chatError}</span>
                <button onClick={clearChatError}>dismiss</button>
              </div>
            )}
            <Composer />
          </div>
          </div>

          {/* Bottom: terminal + runners */}
          {bottomOpen && (
            <div className="flex h-72 shrink-0 flex-col border-t border-edge bg-panel">
              <div className="flex items-center gap-1 border-b border-edge bg-panelalt px-2 py-1 text-xs">
                <button
                  className={
                    "rounded px-2 py-1 " +
                    (bottomTab === "run"
                      ? "bg-edge text-neutral-100"
                      : "text-neutral-400 hover:bg-edge/60")
                  }
                  onClick={() => setBottomTab("run")}
                >
                  Run
                </button>
                <button
                  className={
                    "rounded px-2 py-1 " +
                    (bottomTab === "terminal"
                      ? "bg-edge text-neutral-100"
                      : "text-neutral-400 hover:bg-edge/60")
                  }
                  onClick={() => setBottomTab("terminal")}
                >
                  Terminal
                </button>
                <button
                  className="ml-auto rounded px-2 py-1 text-neutral-400 hover:bg-edge/60"
                  onClick={() => setBottomOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="min-h-0 flex-1">
                {/* Keep both mounted so terminal session + log survive tab switches */}
                <div className={bottomTab === "run" ? "h-full" : "hidden"}>
                  <RunPanel projectId={currentId} />
                </div>
                <div className={bottomTab === "terminal" ? "h-full" : "hidden"}>
                  <Terminal projectId={currentId} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <ConfirmModal />

      {diffCode != null && activeFile && (
        <DiffModal
          path={activeFile.path}
          original={activeFile.content}
          modified={diffCode}
          onClose={() => setDiffCode(null)}
          onApply={() => {
            applyToActive(diffCode);
            if (activePath) void saveFile(activePath);
            setDiffCode(null);
          }}
        />
      )}
    </div>
  );
}

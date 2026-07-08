import { useEffect, useState } from "react";
import { getHealth, type Health } from "./api/client";
import { useSession } from "./stores/session";
import { useProject } from "./stores/project";
import ChatView from "./components/chat/ChatView";
import CodeView from "./components/editor/CodeView";
import AgentsView from "./components/agents/AgentsView";
import AssetsView from "./components/assets/AssetsView";
import BuildView from "./components/build/BuildView";
import PreviewModal from "./components/preview/PreviewModal";
import SettingsModal from "./components/settings/SettingsModal";
import QuickOpen from "./components/editor/QuickOpen";

type Mode = "Chat" | "Code" | "Agents" | "Build" | "Assets";
const MODES: Mode[] = ["Chat", "Code", "Agents", "Build", "Assets"];

export default function App() {
  const [mode, setMode] = useState<Mode>("Chat");
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [quickOpen, setQuickOpen] = useState(false);
  const setModels = useSession((s) => s.setModels);
  const currentProjectId = useProject((s) => s.currentId);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getHealth()
        .then((h) => {
          if (!alive) return;
          setHealth(h);
          setError(null);
          setModels(h.models, h.config.model_big);
        })
        .catch((e) => alive && setError(String(e.message ?? e)));
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [setModels]);

  // Global keyboard shortcuts: Cmd/Ctrl+K new chat, Cmd/Ctrl+P quick-open,
  // Cmd/Ctrl+, settings. (Cmd+` toggles the terminal — handled in Code mode.)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      if (e.key === "k") {
        e.preventDefault();
        setMode("Chat");
        void useSession.getState().newChat();
      } else if (e.key === "p") {
        e.preventDefault();
        if (useProject.getState().currentId != null) {
          setMode("Code");
          setQuickOpen(true);
        }
      } else if (e.key === ",") {
        e.preventDefault();
        setSettingsOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 border-b border-edge bg-panelalt px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold text-accent">◈ Workbench</span>
          <span className="text-xs text-neutral-500">local AI studio</span>
        </div>
        <nav className="flex gap-1">
          {MODES.map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={
                "rounded px-3 py-1 text-sm transition " +
                (mode === m
                  ? "bg-accent text-black"
                  : "text-neutral-300 hover:bg-edge")
              }
            >
              {m}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <StatusPill health={health} error={error} />
          <button
            className="rounded px-2 py-1 text-neutral-400 hover:bg-edge hover:text-neutral-100"
            title="Settings (Ctrl+,)"
            onClick={() => setSettingsOpen(true)}
          >
            ⚙
          </button>
        </div>
      </header>

      <main className="min-h-0 flex-1">
        {mode === "Chat" ? (
          <ChatView />
        ) : mode === "Code" ? (
          <CodeView />
        ) : mode === "Agents" ? (
          <AgentsView />
        ) : mode === "Build" ? (
          <BuildView />
        ) : (
          <AssetsView />
        )}
      </main>

      <PreviewModal />
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
      {quickOpen && currentProjectId != null && (
        <QuickOpen
          projectId={currentProjectId}
          onClose={() => setQuickOpen(false)}
        />
      )}
    </div>
  );
}

function StatusPill({
  health,
  error,
}: {
  health: Health | null;
  error: string | null;
}) {
  const online = !!health && !health.ollama_error && !error;
  const label = error
    ? "backend offline"
    : health?.ollama_error
      ? "ollama offline"
      : health
        ? `${health.models.length} models`
        : "connecting…";
  return (
    <span className="flex items-center gap-2 rounded-full border border-edge px-3 py-1 text-xs">
      <span
        className={
          "inline-block h-2 w-2 rounded-full " +
          (online ? "bg-green-400" : "bg-red-400")
        }
      />
      {label}
    </span>
  );
}


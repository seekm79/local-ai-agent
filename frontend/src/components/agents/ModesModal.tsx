import { useEffect, useState } from "react";
import * as api from "../../api/client";
import { useSession } from "../../stores/session";

const BLANK: api.Mode = {
  slug: "",
  name: "",
  system_prompt: "",
  model: null,
  temperature: null,
  top_p: null,
  allowed_tools: [],
  file_globs: [],
};

export default function ModesModal({ onClose }: { onClose: () => void }) {
  const models = useSession((s) => s.models);
  const [modes, setModes] = useState<api.Mode[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [sel, setSel] = useState<api.Mode | null>(null);
  const [globsText, setGlobsText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reload = () =>
    api.getModes().then((m) => {
      setModes(m);
      setSel((cur) => cur ?? m[0] ?? null);
    });

  useEffect(() => {
    void reload();
    void api.getModeTools().then(setTools);
  }, []);

  useEffect(() => {
    setGlobsText((sel?.file_globs ?? []).join(", "));
  }, [sel?.slug]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const patch = (p: Partial<api.Mode>) => setSel((s) => (s ? { ...s, ...p } : s));

  const toggleTool = (t: string) =>
    setSel((s) =>
      s
        ? {
            ...s,
            allowed_tools: s.allowed_tools.includes(t)
              ? s.allowed_tools.filter((x) => x !== t)
              : [...s.allowed_tools, t],
          }
        : s,
    );

  const save = async () => {
    if (!sel || !sel.slug.trim()) {
      setError("slug is required");
      return;
    }
    setError(null);
    try {
      const payload: api.Mode = {
        ...sel,
        file_globs: globsText.split(/[,\n]/).map((s) => s.trim()).filter(Boolean),
      };
      await api.upsertMode(payload);
      await reload();
    } catch (e) {
      setError(String((e as Error).message));
    }
  };

  const remove = async () => {
    if (!sel || sel.built_in) return;
    if (!confirm(`Delete mode "${sel.name}"?`)) return;
    try {
      await api.deleteMode(sel.slug);
      setSel(null);
      await reload();
    } catch (e) {
      setError(String((e as Error).message));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onClick={onClose}>
      <div
        className="flex h-[80vh] w-full max-w-3xl overflow-hidden rounded-lg border border-edge bg-panel"
        onClick={(e) => e.stopPropagation()}
      >
        {/* left: mode list */}
        <div className="flex w-52 shrink-0 flex-col border-r border-edge bg-panelalt">
          <div className="flex items-center justify-between border-b border-edge px-3 py-2 text-sm">
            <span className="font-medium">Modes</span>
            <button
              className="text-xs text-accent hover:underline"
              onClick={() => setSel({ ...BLANK })}
            >
              + New
            </button>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {modes.map((m) => (
              <button
                key={m.slug}
                className={
                  "flex w-full items-center gap-1 px-3 py-1.5 text-left text-sm " +
                  (sel?.slug === m.slug ? "bg-edge text-neutral-100" : "hover:bg-edge/50")
                }
                onClick={() => setSel(m)}
              >
                <span className="flex-1 truncate">{m.name}</span>
                {m.built_in ? (
                  <span className="text-[10px] text-neutral-500">built-in</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>

        {/* right: editor */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-edge px-4 py-2">
            <span className="text-sm font-medium">Edit mode</span>
            <button className="text-neutral-400 hover:text-white" onClick={onClose}>
              ✕
            </button>
          </div>
          {!sel ? (
            <div className="flex flex-1 items-center justify-center text-neutral-500">
              Select or create a mode.
            </div>
          ) : (
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 text-sm">
              <div className="flex gap-2">
                <label className="flex-1 text-xs text-neutral-400">
                  Slug
                  <input
                    className="mt-1 w-full rounded border border-edge bg-panelalt px-2 py-1 disabled:opacity-60"
                    value={sel.slug}
                    disabled={!!sel.built_in || !!sel.id}
                    onChange={(e) => patch({ slug: e.target.value })}
                  />
                </label>
                <label className="flex-1 text-xs text-neutral-400">
                  Name
                  <input
                    className="mt-1 w-full rounded border border-edge bg-panelalt px-2 py-1"
                    value={sel.name}
                    onChange={(e) => patch({ name: e.target.value })}
                  />
                </label>
              </div>

              <label className="block text-xs text-neutral-400">
                System prompt
                <textarea
                  className="mt-1 h-24 w-full rounded border border-edge bg-panelalt p-2"
                  value={sel.system_prompt}
                  onChange={(e) => patch({ system_prompt: e.target.value })}
                />
              </label>

              <div className="flex gap-2">
                <label className="flex-1 text-xs text-neutral-400">
                  Model (blank = run's model)
                  <input
                    list="wb-mode-models"
                    className="mt-1 w-full rounded border border-edge bg-panelalt px-2 py-1"
                    value={sel.model ?? ""}
                    onChange={(e) => patch({ model: e.target.value || null })}
                  />
                  <datalist id="wb-mode-models">
                    {models.map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                </label>
                <label className="w-24 text-xs text-neutral-400">
                  Temp
                  <input
                    type="number"
                    step={0.1}
                    className="mt-1 w-full rounded border border-edge bg-panelalt px-2 py-1"
                    value={sel.temperature ?? ""}
                    onChange={(e) =>
                      patch({ temperature: e.target.value ? Number(e.target.value) : null })
                    }
                  />
                </label>
              </div>

              <div className="text-xs text-neutral-400">
                Allowed tools
                <div className="mt-1 flex flex-wrap gap-2">
                  {tools.map((t) => (
                    <label key={t} className="flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={sel.allowed_tools.includes(t)}
                        onChange={() => toggleTool(t)}
                      />
                      {t}
                    </label>
                  ))}
                </div>
              </div>

              <label className="block text-xs text-neutral-400">
                File globs (comma-separated; blank = all files)
                <input
                  className="mt-1 w-full rounded border border-edge bg-panelalt px-2 py-1"
                  placeholder="*.md, docs/**"
                  value={globsText}
                  onChange={(e) => setGlobsText(e.target.value)}
                />
              </label>

              {error && <div className="text-red-400">{error}</div>}
            </div>
          )}
          {sel && (
            <div className="flex items-center justify-end gap-2 border-t border-edge px-4 py-2 text-sm">
              {!sel.built_in && sel.id != null && (
                <button className="mr-auto text-red-400 hover:underline" onClick={() => void remove()}>
                  Delete
                </button>
              )}
              <button className="rounded px-3 py-1.5 hover:bg-edge" onClick={onClose}>
                Close
              </button>
              <button
                className="rounded bg-accent px-3 py-1.5 font-medium text-black"
                onClick={() => void save()}
              >
                Save
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

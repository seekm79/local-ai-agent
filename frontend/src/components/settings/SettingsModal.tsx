import { useEffect, useState } from "react";
import * as api from "../../api/client";
import { useSession } from "../../stores/session";

const MODEL_FIELDS: [string, string][] = [
  ["model_big", "Big / primary model"],
  ["model_planner", "Planner model"],
  ["model_coder", "Coder model"],
  ["model_reviewer", "Reviewer model"],
  ["model_helper", "Helper model (summaries)"],
];

const NUM_FIELDS: [string, string, number][] = [
  ["chat_temperature", "Chat temperature", 0.1],
  ["coding_temperature", "Coding temperature", 0.1],
  ["coding_top_p", "Coding top_p", 0.05],
  ["context_char_budget", "Context char budget", 1000],
];

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const models = useSession((s) => s.models);
  const [values, setValues] = useState<api.Settings | null>(null);
  const [denyText, setDenyText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        setValues(s);
        setDenyText(
          Array.isArray(s.deny_commands) ? s.deny_commands.join("\n") : "",
        );
      })
      .catch((e) => setError(String(e.message)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const set = (k: string, v: string | number) =>
    setValues((prev) => (prev ? { ...prev, [k]: v } : prev));

  const save = async () => {
    if (!values) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload: api.Settings = {
        ...values,
        deny_commands: denyText
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      const fresh = await api.updateSettings(payload);
      setValues(fresh);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-edge bg-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-edge px-4 py-2">
          <span className="text-sm font-medium">⚙ Settings</span>
          <button className="text-neutral-400 hover:text-white" onClick={onClose}>
            ✕
          </button>
        </header>

        {!values ? (
          <div className="p-8 text-center text-neutral-500">
            {error ?? "Loading…"}
          </div>
        ) : (
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-sm">
            {/* Installed models available for the datalist */}
            <datalist id="wb-models">
              {models.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>

            <Section title="Paths">
              <Field label="Projects root">
                <input
                  className="w-full rounded border border-edge bg-panelalt px-2 py-1"
                  value={String(values.projects_root ?? "")}
                  onChange={(e) => set("projects_root", e.target.value)}
                />
              </Field>
            </Section>

            <Section title="Model assignments">
              <p className="mb-2 text-xs text-neutral-500">
                Type any Ollama tag, or pick an installed one from the list.
              </p>
              {MODEL_FIELDS.map(([key, label]) => (
                <Field key={key} label={label}>
                  <input
                    list="wb-models"
                    className="w-full rounded border border-edge bg-panelalt px-2 py-1"
                    value={String(values[key] ?? "")}
                    onChange={(e) => set(key, e.target.value)}
                  />
                </Field>
              ))}
            </Section>

            <Section title="Sampling & context">
              {NUM_FIELDS.map(([key, label, step]) => (
                <Field key={key} label={label}>
                  <input
                    type="number"
                    step={step}
                    className="w-40 rounded border border-edge bg-panelalt px-2 py-1"
                    value={String(values[key] ?? "")}
                    onChange={(e) => set(key, Number(e.target.value))}
                  />
                </Field>
              ))}
            </Section>

            <Section title="ComfyUI">
              <Field label="Base URL">
                <input
                  className="w-full rounded border border-edge bg-panelalt px-2 py-1"
                  value={String(values.comfy_base_url ?? "")}
                  onChange={(e) => set("comfy_base_url", e.target.value)}
                />
              </Field>
            </Section>

            <Section title="Command deny-list">
              <p className="mb-1 text-xs text-neutral-500">
                One command per line. These require confirmation before running.
              </p>
              <textarea
                className="h-24 w-full rounded border border-edge bg-panelalt p-2 font-mono text-xs"
                value={denyText}
                onChange={(e) => setDenyText(e.target.value)}
              />
            </Section>

            {error && (
              <div className="rounded border border-red-800 bg-red-950/30 p-2 text-red-300">
                {error}
              </div>
            )}
          </div>
        )}

        <footer className="flex items-center justify-end gap-3 border-t border-edge px-4 py-2 text-sm">
          {saved && <span className="text-green-400">saved ✓ (applied live)</span>}
          <button className="rounded px-3 py-1.5 hover:bg-edge" onClick={onClose}>
            Close
          </button>
          <button
            className="rounded bg-accent px-3 py-1.5 font-medium text-black disabled:opacity-40"
            onClick={() => void save()}
            disabled={saving || !values}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-1 text-xs uppercase tracking-wide text-neutral-500">
        {title}
      </h3>
      <div className="space-y-2 rounded-lg border border-edge bg-panelalt/40 p-3">
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center gap-3">
      <span className="w-44 shrink-0 text-neutral-400">{label}</span>
      <div className="flex-1">{children}</div>
    </label>
  );
}

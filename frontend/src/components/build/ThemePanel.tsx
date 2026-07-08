import { useEffect, useState } from "react";
import * as api from "../../api/client";
import { useBuild } from "../../stores/build";

export default function ThemePanel({
  projectId,
  model,
}: {
  projectId: number;
  model?: string;
}) {
  const regenerate = useBuild((s) => s.regenerateDesign);
  const [palette, setPalette] = useState<api.Palette | null>(null);
  const [mode, setMode] = useState<"light" | "dark">("light");
  const [saved, setSaved] = useState(false);

  const reload = () => api.getPalette(projectId).then(setPalette);
  useEffect(() => {
    void reload();
  }, [projectId]);

  if (!palette) {
    return <div className="p-6 text-neutral-500">Loading palette…</div>;
  }

  const tokens = palette[mode];

  const setToken = (key: string, value: string) =>
    setPalette((p) =>
      p ? { ...p, [mode]: { ...p[mode], [key]: value } } : p,
    );

  const save = async () => {
    const fresh = await api.putPalette(projectId, palette);
    setPalette(fresh);
    setSaved(true);
    setTimeout(() => setSaved(false), 1200);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-edge px-3 py-1.5 text-xs">
        <div className="flex gap-1">
          {(["light", "dark"] as const).map((m) => (
            <button
              key={m}
              className={
                "rounded px-2 py-1 " +
                (mode === m ? "bg-edge text-neutral-100" : "text-neutral-400 hover:bg-edge/60")
              }
              onClick={() => setMode(m)}
            >
              {m}
            </button>
          ))}
        </div>
        <label className="ml-2 flex items-center gap-1 text-neutral-400">
          radius
          <input
            className="w-20 rounded border border-edge bg-panel px-1 py-0.5"
            value={palette.radius}
            onChange={(e) => setPalette((p) => (p ? { ...p, radius: e.target.value } : p))}
          />
        </label>
        {saved && <span className="text-green-400">saved ✓</span>}
        <div className="ml-auto flex gap-2">
          <button
            className="rounded px-2 py-1 text-neutral-300 hover:bg-edge"
            onClick={() => regenerate(model)}
            title="Re-run only the Designer with a new palette"
          >
            ↻ Regenerate design
          </button>
          <button
            className="rounded bg-accent px-3 py-1 font-medium text-black"
            onClick={() => void save()}
          >
            Apply
          </button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-2 content-start gap-2 overflow-y-auto p-3 md:grid-cols-3">
        {Object.entries(tokens).map(([key, value]) => (
          <div key={key} className="rounded border border-edge bg-panelalt p-2">
            <div className="mb-1 flex items-center gap-2">
              <span
                className="inline-block h-5 w-5 shrink-0 rounded border border-edge"
                style={{ background: value }}
                title={value}
              />
              <span className="truncate text-[11px] text-neutral-400">{key}</span>
            </div>
            <input
              className="w-full rounded border border-edge bg-panel px-1 py-0.5 font-mono text-[10px]"
              value={value}
              onChange={(e) => setToken(key, e.target.value)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

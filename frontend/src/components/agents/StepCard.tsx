import { useState } from "react";
import type { StepView } from "../../stores/agents";
import { usePreview } from "../../stores/preview";

function statusColor(status: string): string {
  if (status === "passed") return "border-green-600 bg-green-950/30";
  if (status === "failed") return "border-red-700 bg-red-950/30";
  if (status === "running" || status.startsWith("fixing"))
    return "border-accent bg-accent/10";
  return "border-edge bg-panelalt";
}

function statusDot(status: string): string {
  if (status === "passed") return "bg-green-400";
  if (status === "failed") return "bg-red-400";
  if (status === "running" || status.startsWith("fixing"))
    return "bg-accent animate-pulse";
  return "bg-neutral-600";
}

export default function StepCard({ step, index }: { step: StepView; index: number }) {
  const [open, setOpen] = useState(false);
  const openPreview = usePreview((s) => s.open);
  const hasDetail = step.messages.length > 0 || step.tools.length > 0;

  return (
    <div className={"rounded-lg border " + statusColor(step.status)}>
      <button
        className="flex w-full items-center gap-3 px-3 py-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={"inline-block h-2.5 w-2.5 shrink-0 rounded-full " + statusDot(step.status)}
        />
        <span className="shrink-0 text-xs text-neutral-500">#{index + 1}</span>
        <span className="rounded bg-edge px-1.5 py-0.5 text-[10px] uppercase text-neutral-400">
          {step.kind}
        </span>
        <span className="flex-1 truncate text-sm">{step.title}</span>
        <span className="shrink-0 text-xs text-neutral-400">{step.status}</span>
        {hasDetail && (
          <span className="shrink-0 text-neutral-500">{open ? "▾" : "▸"}</span>
        )}
      </button>

      {open && (
        <div className="space-y-2 border-t border-edge/60 px-3 py-2 text-xs">
          {step.detail && <p className="text-neutral-400">{step.detail}</p>}
          {step.targetFiles.length > 0 && (
            <p className="text-neutral-500">
              targets: {step.targetFiles.join(", ")}
            </p>
          )}

          {step.tools.map((t, i) => (
            <div key={i} className="rounded border border-edge bg-panel p-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-accent">{t.tool}</span>
                {t.args?.path && <span className="text-neutral-400">{t.args.path}</span>}
                {t.args?.argv && (
                  <span className="text-neutral-400">{t.args.argv.join(" ")}</span>
                )}
                {t.ok !== undefined && (
                  <span className={t.ok ? "text-green-400" : "text-red-400"}>
                    {t.ok ? "ok" : "fail"}
                  </span>
                )}
                {t.before !== undefined && t.after !== undefined && (
                  <button
                    className="ml-auto text-accent hover:underline"
                    onClick={() =>
                      openPreview({
                        kind: "diff",
                        path: t.path ?? "file",
                        before: t.before ?? "",
                        after: t.after ?? "",
                        title: `diff · ${t.path ?? ""}`,
                      })
                    }
                  >
                    view diff
                  </button>
                )}
              </div>
              {t.output && (
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-neutral-400">
                  {t.output}
                </pre>
              )}
              {t.screenshots && t.screenshots.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {t.screenshots.map((src) => (
                    <img
                      key={src}
                      src={src}
                      alt="browser screenshot"
                      className="max-h-48 cursor-pointer rounded border border-edge"
                      onClick={() =>
                        openPreview({ kind: "image", src, title: "browser screenshot" })
                      }
                    />
                  ))}
                </div>
              )}
            </div>
          ))}

          {step.messages.map((m, i) => (
            <details key={"m" + i} className="rounded border border-edge bg-panel p-2">
              <summary className="cursor-pointer text-neutral-400">
                {m.role} output
              </summary>
              <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap text-neutral-300">
                {m.content}
              </pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { useRun } from "../../stores/run";
import { usePreview } from "../../stores/preview";

// Strip ANSI/CSI escape sequences for the plain run-output log.
const stripAnsi = (s: string) =>
  s.replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, "").replace(/\x1b\][^\x07]*\x07/g, "");

export default function RunPanel({ projectId }: { projectId: number }) {
  const {
    runners,
    processes,
    connect,
    detect,
    runProject,
    runCommand,
    stop,
    onOutput,
  } = useRun();
  const openPreview = usePreview((s) => s.open);
  const [cmd, setCmd] = useState("");
  const [log, setLog] = useState("");
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    connect();
    void detect(projectId);
  }, [projectId, connect, detect]);

  useEffect(
    () =>
      onOutput((_pid, data) =>
        setLog((l) => (l + stripAnsi(data)).slice(-40000)),
      ),
    [onOutput],
  );

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  const projProcs = processes
    .filter((p) => p.project_id === projectId)
    .sort((a, b) => b.id - a.id);

  const submitCmd = () => {
    const argv = cmd.trim().split(/\s+/).filter(Boolean);
    if (argv.length) {
      void runCommand(projectId, argv);
      setCmd("");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col text-sm">
      {/* Runner buttons + command box */}
      <div className="flex flex-wrap items-center gap-2 border-b border-edge px-3 py-2">
        {runners.length === 0 && (
          <span className="text-xs text-neutral-500">
            No runnable project type detected (add a .csproj, package.json,
            pubspec.yaml, or project.godot).
          </span>
        )}
        {runners.map((r) => (
          <button
            key={r.kind}
            disabled={!r.available}
            title={r.available ? r.argv.join(" ") : `${r.missing_tool} not found`}
            onClick={() => void runProject(projectId, r.kind)}
            className={
              "rounded px-2 py-1 text-xs " +
              (r.available
                ? "bg-accent/20 text-accent hover:bg-accent/30"
                : "cursor-not-allowed bg-edge/40 text-neutral-500")
            }
          >
            ▶ {r.label}
            {!r.available && " (missing)"}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-1">
          <input
            className="w-64 rounded border border-edge bg-panel px-2 py-1 text-xs"
            placeholder="run a command, e.g. dotnet build"
            value={cmd}
            onChange={(e) => setCmd(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitCmd()}
          />
          <button
            className="rounded bg-edge px-2 py-1 text-xs hover:bg-edge/70"
            onClick={submitCmd}
          >
            Run
          </button>
        </div>
      </div>

      {/* Process list */}
      {projProcs.length > 0 && (
        <div className="max-h-32 shrink-0 overflow-y-auto border-b border-edge px-3 py-1">
          {projProcs.map((p) => (
            <div
              key={p.id}
              className="flex items-center gap-2 py-0.5 text-xs"
            >
              <StatusBadge status={p.status} code={p.exit_code} />
              <span className="truncate text-neutral-300">{p.name}</span>
              {p.pid && <span className="text-neutral-600">pid {p.pid}</span>}
              {p.dev_url && (
                <button
                  className="text-accent hover:underline"
                  onClick={() =>
                    openPreview({
                      kind: "url",
                      url: p.dev_url!,
                      title: p.dev_url!,
                    })
                  }
                >
                  ▶ Open preview ({p.dev_url})
                </button>
              )}
              {p.status === "running" && (
                <button
                  className="ml-auto rounded bg-red-500/80 px-2 py-0.5 text-white hover:bg-red-500"
                  onClick={() => void stop(p.id)}
                >
                  Stop
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Output log */}
      <pre
        ref={logRef}
        className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap bg-panelalt p-3 font-mono text-xs leading-relaxed text-neutral-300"
      >
        {log || "(process output appears here)"}
      </pre>
    </div>
  );
}

function StatusBadge({
  status,
  code,
}: {
  status: string;
  code: number | null;
}) {
  const cls =
    status === "running"
      ? "bg-green-500/20 text-green-300"
      : status === "killed"
        ? "bg-amber-500/20 text-amber-300"
        : code === 0
          ? "bg-neutral-500/20 text-neutral-300"
          : "bg-red-500/20 text-red-300";
  const label =
    status === "running"
      ? "running"
      : status === "killed"
        ? "stopped"
        : `exit ${code}`;
  return <span className={"rounded px-1.5 py-0.5 " + cls}>{label}</span>;
}

import { useRun } from "../../stores/run";

// Dangerous-command confirmation (Global rule 3). Shown when the backend
// returns needs_confirmation for a deny-listed command.
export default function ConfirmModal() {
  const { confirm, confirmRun, cancelConfirm } = useRun();
  if (!confirm) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-8">
      <div className="w-full max-w-lg rounded-lg border border-amber-700 bg-panel p-5">
        <h3 className="mb-2 text-lg font-medium text-amber-300">
          ⚠ Confirm dangerous command
        </h3>
        <p className="mb-3 text-sm text-neutral-400">
          This command matched the deny-list and needs your approval before it
          runs:
        </p>
        <pre className="mb-4 overflow-x-auto rounded border border-edge bg-panelalt p-3 text-sm text-amber-200">
          {confirm.command}
        </pre>
        <div className="flex justify-end gap-2 text-sm">
          <button
            className="rounded px-3 py-1.5 hover:bg-edge"
            onClick={cancelConfirm}
          >
            Cancel
          </button>
          <button
            className="rounded bg-amber-600 px-3 py-1.5 font-medium text-black hover:bg-amber-500"
            onClick={() => void confirmRun()}
          >
            Run anyway
          </button>
        </div>
      </div>
    </div>
  );
}

import { useState } from "react";
import { useSession } from "../../stores/session";

export default function Composer() {
  const { models, model, setModel, think, toggleThink, streaming, send, stop } =
    useSession();
  const [text, setText] = useState("");

  const submit = () => {
    const t = text.trim();
    if (!t || streaming) return;
    setText("");
    void send(t);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-edge bg-panelalt p-3">
      <div className="mb-2 flex items-center gap-3 text-xs">
        <label className="flex items-center gap-1 text-neutral-400">
          model
          <select
            className="rounded border border-edge bg-panel px-2 py-1 text-neutral-200"
            value={model ?? ""}
            onChange={(e) => setModel(e.target.value)}
            disabled={models.length === 0}
          >
            {models.length === 0 && <option value="">no models</option>}
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>

        <label className="flex cursor-pointer items-center gap-1 text-neutral-400">
          <input type="checkbox" checked={think} onChange={toggleThink} />
          thinking
        </label>
      </div>

      <div className="flex items-end gap-2">
        <textarea
          className="flex-1 resize-none rounded-md border border-edge bg-panel p-2 text-sm outline-none focus:border-accent"
          rows={2}
          placeholder="Message… (Enter to send, Shift+Enter for newline)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
        />
        {streaming ? (
          <button
            onClick={stop}
            className="rounded-md bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600"
          >
            Stop
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!text.trim() || !model}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-black disabled:opacity-40"
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}

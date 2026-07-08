import { useState } from "react";
import { useSession } from "../../stores/session";

export default function ChatSidebar() {
  const {
    chats,
    currentChatId,
    newChat,
    selectChat,
    renameChat,
    deleteChat,
  } = useSession();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-edge bg-panelalt">
      <div className="p-2">
        <button
          onClick={() => void newChat()}
          className="w-full rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-black hover:opacity-90"
        >
          + New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {chats.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-neutral-500">
            No chats yet.
          </p>
        )}
        {chats.map((c) => (
          <div
            key={c.id}
            className={
              "group mb-1 flex items-center gap-1 rounded-md px-2 py-1.5 text-sm " +
              (c.id === currentChatId
                ? "bg-edge text-neutral-100"
                : "text-neutral-300 hover:bg-edge/60")
            }
          >
            {editingId === c.id ? (
              <input
                className="w-full rounded border border-edge bg-panel px-1 text-sm"
                value={draft}
                autoFocus
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => {
                  setEditingId(null);
                  if (draft.trim()) void renameChat(c.id, draft.trim());
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  if (e.key === "Escape") setEditingId(null);
                }}
              />
            ) : (
              <button
                className="flex-1 truncate text-left"
                onClick={() => void selectChat(c.id)}
                onDoubleClick={() => {
                  setEditingId(c.id);
                  setDraft(c.title);
                }}
                title={c.title}
              >
                {c.title}
              </button>
            )}
            <button
              className="opacity-0 group-hover:opacity-100 hover:text-red-400"
              title="Delete chat"
              onClick={() => {
                if (confirm(`Delete chat "${c.title}"?`)) void deleteChat(c.id);
              }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
